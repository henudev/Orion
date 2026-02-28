from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    BUILD_STATUS_FAILED,
    BUILD_STATUS_QUEUED,
    BUILD_STATUS_RUNNING,
    BUILD_STATUS_SUCCESS,
)
from app.core.logging import get_daily_log_file, write_build_log
from app.db.session import SessionLocal
from app.models.app import App
from app.models.build import Build
from app.schemas.build import BuildCreate
from app.services.command_runner import run_simple_command, run_streaming_command
from app.services.log_stream import log_broker


@dataclass
class BuildTask:
    build_id: int
    payload: BuildCreate


build_queue: asyncio.Queue[BuildTask] = asyncio.Queue()
build_workers: list[asyncio.Task[None]] = []


def create_build_record(session: Session, payload: BuildCreate) -> Build:
    build = Build(
        app_id=payload.app_id,
        image_tag=payload.image_tag,
        image_digest=None,
        status=BUILD_STATUS_QUEUED,
        log_file=str(get_daily_log_file("build")),
    )
    session.add(build)
    session.commit()
    session.refresh(build)
    return build


async def enqueue_build(build_id: int, payload: BuildCreate) -> None:
    await build_queue.put(BuildTask(build_id=build_id, payload=payload))
    await _emit_log(build_id, "Build queued.")


async def start_build_workers() -> None:
    if build_workers:
        return
    for idx in range(settings.max_concurrent_builds):
        worker = asyncio.create_task(_build_worker(idx), name=f"build-worker-{idx}")
        build_workers.append(worker)


async def stop_build_workers() -> None:
    for worker in build_workers:
        worker.cancel()
    if build_workers:
        await asyncio.gather(*build_workers, return_exceptions=True)
    build_workers.clear()


async def _build_worker(worker_id: int) -> None:
    while True:
        task = await build_queue.get()
        try:
            await _process_build_task(task, worker_id)
        except Exception as exc:  # noqa: BLE001
            with SessionLocal() as session:
                build = session.get(Build, task.build_id)
                if build:
                    build.status = BUILD_STATUS_FAILED
                    build.error_message = str(exc)
                    session.commit()
            await _emit_log(task.build_id, f"Build failed unexpectedly: {exc}")
        finally:
            build_queue.task_done()


async def _process_build_task(task: BuildTask, worker_id: int) -> None:
    with SessionLocal() as session:
        build = session.get(Build, task.build_id)
        if build is None:
            return

        app = session.get(App, build.app_id)
        if app is None:
            build.status = BUILD_STATUS_FAILED
            build.error_message = f"App {build.app_id} not found"
            session.commit()
            await _emit_log(build.id, build.error_message)
            return

        build.status = BUILD_STATUS_RUNNING
        session.commit()

        context_path = Path(task.payload.context_path).expanduser() if task.payload.context_path else settings.workspace_dir / app.name
        if not context_path.exists():
            build.status = BUILD_STATUS_FAILED
            build.error_message = f"Build context not found: {context_path}"
            session.commit()
            await _emit_log(build.id, build.error_message)
            return

        build_dir = settings.builds_dir / str(build.id)
        build_dir.mkdir(parents=True, exist_ok=True)

        dockerfile_override: Path | None = None
        if task.payload.dockerfile_content:
            dockerfile_override = build_dir / "Dockerfile"
            dockerfile_override.write_text(task.payload.dockerfile_content, encoding="utf-8")

        timeout = task.payload.timeout_seconds or settings.build_timeout_seconds
        command = ["docker", "build", "-t", task.payload.image_tag]
        for key, value in task.payload.build_args.items():
            command.extend(["--build-arg", f"{key}={value}"])
        if dockerfile_override is not None:
            command.extend(["-f", str(dockerfile_override)])
        command.append(str(context_path))

        await _emit_log(build.id, f"Worker {worker_id} running: {' '.join(command)}")

        try:
            return_code = await run_streaming_command(
                command,
                on_line=lambda line: _emit_log(build.id, line),
                timeout_seconds=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            build.status = BUILD_STATUS_FAILED
            build.error_message = str(exc)
            session.commit()
            await _emit_log(build.id, f"Build timeout or execution error: {exc}")
            return

        if return_code != 0:
            build.status = BUILD_STATUS_FAILED
            build.error_message = f"docker build failed with exit code {return_code}"
            session.commit()
            await _emit_log(build.id, build.error_message)
            return

        digest_code, digest_out = await run_simple_command(
            [
                "docker",
                "image",
                "inspect",
                task.payload.image_tag,
                "--format",
                "{{index .RepoDigests 0}}",
            ],
            timeout_seconds=20,
        )
        if digest_code == 0 and digest_out:
            build.image_digest = digest_out
            await _emit_log(build.id, f"Image digest: {digest_out}")
        else:
            await _emit_log(build.id, "Image digest unavailable (RepoDigests may be empty for local-only tag).")

        build.status = BUILD_STATUS_SUCCESS
        build.error_message = None
        session.commit()
        await _emit_log(build.id, "Build completed successfully.")


async def _emit_log(build_id: int, line: str) -> None:
    write_build_log(build_id, line)
    await log_broker.publish(f"build:{build_id}", line)


def get_build_queue_size() -> int:
    return build_queue.qsize()


def ensure_app_exists(session: Session, app_id: int) -> bool:
    return session.get(App, app_id) is not None


def build_status_summary() -> dict[str, int]:
    return {"queued": build_queue.qsize(), "workers": len(build_workers)}


def create_build_if_app_exists(session: Session, payload: BuildCreate) -> Build:
    if not ensure_app_exists(session, payload.app_id):
        raise ValueError(f"App {payload.app_id} not found")
    return create_build_record(session, payload)


def is_build_queued_or_running(session: Session, build_id: int) -> bool:
    build = session.get(Build, build_id)
    if build is None:
        return False
    return build.status in {BUILD_STATUS_QUEUED, BUILD_STATUS_RUNNING}

