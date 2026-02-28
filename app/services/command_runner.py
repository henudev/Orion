from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


LineHandler = Callable[[str], Awaitable[None]]


async def run_streaming_command(
    cmd: list[str],
    on_line: LineHandler,
    timeout_seconds: int,
) -> int:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def _read_output() -> None:
        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            await on_line(line.decode(errors="replace").rstrip())

    reader_task = asyncio.create_task(_read_output())
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await on_line(f"Command timeout after {timeout_seconds}s: {' '.join(cmd)}")
        raise
    finally:
        await reader_task

    return process.returncode


async def run_simple_command(cmd: list[str], timeout_seconds: int = 30) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    try:
        raw_output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        raise

    return process.returncode, raw_output.decode(errors="replace").strip()

