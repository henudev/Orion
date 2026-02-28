from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.environment import Environment
from app.schemas.precheck import PrecheckItem, PrecheckResponse
from app.services.command_runner import run_simple_command
from app.services.ssh_service import connect_environment_ssh


async def _safe_run(cmd: list[str], timeout_seconds: int) -> tuple[int, str]:
    try:
        return await run_simple_command(cmd, timeout_seconds=timeout_seconds)
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


async def local_precheck(orion_home: Path) -> PrecheckResponse:
    items: list[PrecheckItem] = []

    docker_info_code, docker_info_out = await _safe_run(["docker", "info"], timeout_seconds=15)
    items.append(
        PrecheckItem(
            name="docker_daemon",
            ok=docker_info_code == 0,
            detail="Docker daemon is running" if docker_info_code == 0 else docker_info_out,
        )
    )

    docker_version_code, docker_version_out = await _safe_run(["docker", "--version"], timeout_seconds=10)
    items.append(
        PrecheckItem(
            name="docker_version",
            ok=docker_version_code == 0,
            detail=docker_version_out if docker_version_out else "docker --version failed",
        )
    )

    usage = shutil.disk_usage(orion_home)
    free_gb = usage.free / (1024**3)
    items.append(
        PrecheckItem(
            name="disk_space",
            ok=free_gb > 5,
            detail=f"free {free_gb:.2f} GiB",
        )
    )

    cache_code, cache_out = await _safe_run(["docker", "system", "df"], timeout_seconds=15)
    items.append(
        PrecheckItem(
            name="builder_cache",
            ok=cache_code == 0,
            detail=cache_out if cache_code == 0 else "docker system df failed",
        )
    )

    docker_socket = Path("/var/run/docker.sock")
    socket_ok = docker_socket.exists() and os.access(docker_socket, os.R_OK | os.W_OK)
    socket_detail = "docker.sock is accessible" if socket_ok else "docker.sock not accessible"
    if docker_socket.exists():
        mode = stat.filemode(docker_socket.stat().st_mode)
        socket_detail = f"{socket_detail}, mode={mode}"
    items.append(PrecheckItem(name="docker_socket_permission", ok=socket_ok, detail=socket_detail))

    return PrecheckResponse(ok=all(item.ok for item in items), items=items)


def remote_precheck(session: Session, env_id: int) -> PrecheckResponse:
    env = session.get(Environment, env_id)
    if env is None:
        return PrecheckResponse(ok=False, items=[PrecheckItem(name="environment", ok=False, detail="not found")])

    items: list[PrecheckItem] = []

    if not env.password:
        return PrecheckResponse(
            ok=False,
            items=[PrecheckItem(name="ssh_password", ok=False, detail="password is empty")],
        )

    ssh = None
    try:
        ssh = connect_environment_ssh(env, timeout=10)
        items.append(PrecheckItem(name="ssh_connection", ok=True, detail="connected"))

        for name, command in [
            ("docker_available", "docker --version"),
            ("compose_available", "docker compose version"),
            ("disk_space", "df -h /"),
        ]:
            _, stdout, stderr = ssh.exec_command(command, timeout=15)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            items.append(
                PrecheckItem(
                    name=name,
                    ok=exit_code == 0,
                    detail=output if exit_code == 0 else err or output,
                )
            )
    except Exception as exc:  # noqa: BLE001
        items.append(PrecheckItem(name="ssh_connection", ok=False, detail=str(exc)))
    finally:
        if ssh is not None:
            ssh.close()

    return PrecheckResponse(ok=all(item.ok for item in items), items=items)
