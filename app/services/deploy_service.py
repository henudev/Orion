from __future__ import annotations

import asyncio
import shlex
import subprocess
import time

import paramiko
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    DEPLOY_STATUS_FAILED,
    DEPLOY_STATUS_QUEUED,
    DEPLOY_STATUS_RUNNING,
    DEPLOY_STATUS_SUCCESS,
)
from app.core.logging import get_daily_log_file, write_deploy_log
from app.db.session import SessionLocal
from app.models.app import App
from app.models.build import Build
from app.models.deployment import Deployment
from app.models.environment import Environment
from app.schemas.deployment import DeployCreate
from app.services.locks import deploy_locks
from app.services.log_stream import log_broker
from app.services.ssh_service import connect_environment_ssh


def create_deployment_record(session: Session, payload: DeployCreate, image_digest: str | None) -> Deployment:
    deployment = Deployment(
        app_id=payload.app_id,
        environment_id=payload.environment_id,
        image_digest=image_digest,
        mode=payload.mode,
        status=DEPLOY_STATUS_QUEUED,
        log_file=str(get_daily_log_file("deploy")),
    )
    session.add(deployment)
    session.commit()
    session.refresh(deployment)
    return deployment


def validate_deploy_request(session: Session, payload: DeployCreate) -> tuple[App, Environment]:
    app = session.get(App, payload.app_id)
    env = session.get(Environment, payload.environment_id)
    if app is None:
        raise ValueError(f"App {payload.app_id} not found")
    if env is None:
        raise ValueError(f"Environment {payload.environment_id} not found")
    return app, env


def resolve_image_ref(session: Session, payload: DeployCreate) -> tuple[str, str | None]:
    if payload.image_ref:
        return payload.image_ref, payload.image_ref if "@sha256:" in payload.image_ref else None

    if payload.build_id is None:
        raise ValueError("Either image_ref or build_id must be provided")

    build = session.get(Build, payload.build_id)
    if build is None:
        raise ValueError(f"Build {payload.build_id} not found")
    if build.status != "success":
        raise ValueError(f"Build {payload.build_id} is not successful")

    image_ref = build.image_digest or build.image_tag
    return image_ref, build.image_digest


async def process_deployment(deployment_id: int, payload: DeployCreate, image_ref: str) -> None:
    lock_key = f"{payload.app_id}:{payload.environment_id}"
    lock = deploy_locks[lock_key]
    async with lock:
        with SessionLocal() as session:
            deployment = session.get(Deployment, deployment_id)
            if deployment is None:
                return
            deployment.status = DEPLOY_STATUS_RUNNING
            session.commit()

        await _emit_log(deployment_id, f"Start deployment with image: {image_ref}")
        try:
            await asyncio.to_thread(_execute_deployment_sync, deployment_id, payload, image_ref)
            with SessionLocal() as session:
                deployment = session.get(Deployment, deployment_id)
                if deployment:
                    deployment.status = DEPLOY_STATUS_SUCCESS
                    deployment.error_message = None
                    session.commit()
            await _emit_log(deployment_id, "Deployment finished successfully.")
        except Exception as exc:  # noqa: BLE001
            with SessionLocal() as session:
                deployment = session.get(Deployment, deployment_id)
                if deployment:
                    deployment.status = DEPLOY_STATUS_FAILED
                    deployment.error_message = str(exc)
                    session.commit()
            await _emit_log(deployment_id, f"Deployment failed: {exc}")


def _execute_deployment_sync(deployment_id: int, payload: DeployCreate, image_ref: str) -> None:
    with SessionLocal() as session:
        app = session.get(App, payload.app_id)
        env = session.get(Environment, payload.environment_id)
    if app is None or env is None:
        raise RuntimeError("App or environment missing")

    ssh = _connect_paramiko(env)
    try:
        _stream_image_to_remote(ssh, deployment_id, image_ref)
        if payload.mode == "run":
            _deploy_with_run(ssh, deployment_id, payload, image_ref)
        else:
            _deploy_with_compose(ssh, deployment_id, app.name, env.name, payload, image_ref)
    finally:
        ssh.close()


def _stream_image_to_remote(ssh: paramiko.SSHClient, deployment_id: int, image_ref: str) -> None:
    save_cmd = ["docker", "save", image_ref]
    _emit_log_sync(deployment_id, f"Streaming image to remote: {' '.join(save_cmd)} -> remote docker load")

    save_proc = subprocess.Popen(save_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # noqa: S603
    assert save_proc.stdout is not None
    assert save_proc.stderr is not None

    transport = ssh.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport unavailable")

    channel = transport.open_session()
    channel.exec_command("docker load")
    remote_output: list[str] = []

    try:
        while True:
            chunk = save_proc.stdout.read(1024 * 1024)
            if not chunk:
                break
            channel.sendall(chunk)
        channel.shutdown_write()

        while True:
            if channel.recv_ready():
                data = channel.recv(65536).decode(errors="replace")
                if data:
                    remote_output.append(data)
            if channel.recv_stderr_ready():
                data = channel.recv_stderr(65536).decode(errors="replace")
                if data:
                    remote_output.append(data)
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            time.sleep(0.05)
        ssh_exit = channel.recv_exit_status()
    finally:
        channel.close()

    save_stderr = save_proc.stderr.read().decode(errors="replace").strip()
    save_exit = save_proc.wait()

    if save_stderr:
        _emit_log_sync(deployment_id, f"[docker save] {save_stderr}")
    if remote_output:
        for line in "".join(remote_output).splitlines():
            if line.strip():
                _emit_log_sync(deployment_id, f"[docker load] {line.strip()}")

    if save_exit != 0:
        raise RuntimeError(f"docker save failed with exit code {save_exit}")
    if ssh_exit != 0:
        raise RuntimeError(f"remote docker load failed with exit code {ssh_exit}")


def _connect_paramiko(env: Environment) -> paramiko.SSHClient:
    return connect_environment_ssh(env, timeout=20)


def _deploy_with_run(
    ssh: paramiko.SSHClient,
    deployment_id: int,
    payload: DeployCreate,
    image_ref: str,
) -> None:
    container_name = payload.container_name or "app-prod"

    rm_cmd = f"docker rm -f {shlex.quote(container_name)}"
    _run_remote_command(ssh, deployment_id, rm_cmd, ignore_error=True)

    run_parts: list[str] = ["docker", "run", "-d", "--name", shlex.quote(container_name)]
    for port in payload.ports:
        run_parts.extend(["-p", shlex.quote(port)])
    for key, value in payload.env_vars.items():
        run_parts.extend(["-e", shlex.quote(f"{key}={value}")])
    run_parts.append(shlex.quote(image_ref))
    run_cmd = " ".join(run_parts)

    _run_remote_command(ssh, deployment_id, run_cmd, ignore_error=False)


def _deploy_with_compose(
    ssh: paramiko.SSHClient,
    deployment_id: int,
    app_name: str,
    env_name: str,
    payload: DeployCreate,
    image_ref: str,
) -> None:
    local_compose_dir = settings.compose_dir / app_name / env_name
    local_compose_dir.mkdir(parents=True, exist_ok=True)
    local_compose_path = local_compose_dir / "compose.yml"

    if payload.compose_content:
        compose_content = payload.compose_content
    else:
        compose_content = (
            "services:\n"
            f"  {app_name}:\n"
            f"    image: {image_ref}\n"
            "    restart: always\n"
        )
    local_compose_path.write_text(compose_content, encoding="utf-8")
    _emit_log_sync(deployment_id, f"Compose file written: {local_compose_path}")

    remote_dir = payload.remote_dir or f"/opt/orion/{app_name}/{env_name}"
    remote_file = f"{remote_dir.rstrip('/')}/compose.yml"
    _mkdir_remote_dir(ssh, remote_dir)
    _upload_file(ssh, str(local_compose_path), remote_file)
    _emit_log_sync(deployment_id, f"Compose uploaded: {remote_file}")

    compose_cmd = f"docker compose -f {shlex.quote(remote_file)} up -d"
    _run_remote_command(ssh, deployment_id, compose_cmd, ignore_error=False)


def _run_remote_command(
    ssh: paramiko.SSHClient,
    deployment_id: int,
    command: str,
    ignore_error: bool,
) -> None:
    _emit_log_sync(deployment_id, f"[remote] {command}")
    _, stdout, stderr = ssh.exec_command(command, timeout=settings.deploy_timeout_seconds)
    exit_status = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()

    if out:
        _emit_log_sync(deployment_id, out)
    if err:
        _emit_log_sync(deployment_id, err)

    if exit_status != 0 and not ignore_error:
        raise RuntimeError(f"Remote command failed ({exit_status}): {command}")


def _mkdir_remote_dir(ssh: paramiko.SSHClient, remote_dir: str) -> None:
    sftp = ssh.open_sftp()
    try:
        segments = remote_dir.strip("/").split("/")
        current = ""
        for segment in segments:
            current = f"{current}/{segment}"
            try:
                sftp.stat(current)
            except OSError:
                sftp.mkdir(current)
    finally:
        sftp.close()


def _upload_file(ssh: paramiko.SSHClient, local_file: str, remote_file: str) -> None:
    sftp = ssh.open_sftp()
    try:
        sftp.put(local_file, remote_file)
    finally:
        sftp.close()


async def _emit_log(deployment_id: int, line: str) -> None:
    write_deploy_log(deployment_id, line)
    await log_broker.publish(f"deploy:{deployment_id}", line)


def _emit_log_sync(deployment_id: int, line: str) -> None:
    write_deploy_log(deployment_id, line)
