from __future__ import annotations

import paramiko

from app.models.environment import Environment
from app.schemas.environment import EnvironmentConnectionTestResponse


def test_ssh_connection(
    host: str,
    port: int,
    username: str,
    password: str,
    timeout: int = 10,
) -> EnvironmentConnectionTestResponse:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=timeout,
        )
        _, stdout, _ = ssh.exec_command("echo ORION_SSH_OK", timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        output = stdout.read().decode(errors="replace").strip()
        if exit_code == 0:
            return EnvironmentConnectionTestResponse(ok=True, detail=output or "connection success")
        return EnvironmentConnectionTestResponse(ok=False, detail=f"connected, but command failed ({exit_code})")
    except Exception as exc:  # noqa: BLE001
        return EnvironmentConnectionTestResponse(ok=False, detail=str(exc))
    finally:
        ssh.close()


def connect_environment_ssh(env: Environment, timeout: int = 20) -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname=env.host,
        port=env.port,
        username=env.username,
        password=env.password,
        look_for_keys=False,
        allow_agent=False,
        timeout=timeout,
    )
    return ssh

