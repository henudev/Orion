from __future__ import annotations

from pathlib import Path


def read_lines_by_marker(log_file: str, marker: str, tail: int = 200) -> list[str]:
    path = Path(log_file)
    if not path.exists():
        return []

    matched: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if marker in line:
                matched.append(line.rstrip())
    return matched[-tail:]

