from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.timezone import to_orion
from app.services.command_runner import run_simple_command


def _normalize_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _short_image_id(full_id: str) -> str:
    normalized = full_id.replace("sha256:", "")
    return normalized[:12]


def _resolve_image_ref(repository: str, tag: str, digest: str | None, image_id_full: str) -> str:
    if repository != "<none>" and tag != "<none>":
        return f"{repository}:{tag}"
    if repository != "<none>" and digest:
        return f"{repository}@{digest}"
    return image_id_full


def _extract_digest(repo_digests: list[str], repository: str, fallback: str | None) -> str | None:
    if fallback:
        return fallback
    if repository == "<none>":
        return None
    for item in repo_digests:
        if item.startswith(f"{repository}@") and "@sha256:" in item:
            return item.split("@", 1)[1]
    return None


async def list_local_images(limit: int | None = None) -> list[dict[str, Any]]:
    code, out = await run_simple_command(
        ["docker", "image", "ls", "--no-trunc", "--format", "{{json .}}"],
        timeout_seconds=30,
    )
    if code != 0:
        raise RuntimeError(out or "docker image ls failed")

    rows: list[dict[str, Any]] = []
    image_ids: list[str] = []
    for raw_line in out.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        image_id_full = str(item.get("ID") or "").strip()
        if not image_id_full:
            continue

        rows.append(
            {
                "repository": str(item.get("Repository") or "<none>"),
                "tag": str(item.get("Tag") or "<none>"),
                "digest": None if str(item.get("Digest") or "<none>") == "<none>" else str(item.get("Digest")),
                "image_id_full": image_id_full,
            }
        )
        image_ids.append(image_id_full)

    if not rows:
        return []

    inspect_map: dict[str, dict[str, Any]] = {}
    dedup_ids = list(dict.fromkeys(image_ids))
    inspect_code, inspect_out = await run_simple_command(
        ["docker", "image", "inspect", *dedup_ids, "--format", "{{json .}}"],
        timeout_seconds=60,
    )
    if inspect_code == 0:
        for raw_line in inspect_out.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            full_id = str(obj.get("Id") or "")
            if not full_id:
                continue
            inspect_map[full_id] = {
                "created_at": _normalize_datetime(str(obj.get("Created") or "")),
                "size_bytes": obj.get("Size") if isinstance(obj.get("Size"), int) else None,
                "repo_digests": obj.get("RepoDigests") if isinstance(obj.get("RepoDigests"), list) else [],
            }

    images: list[dict[str, Any]] = []
    for row in rows:
        full_id = row["image_id_full"]
        inspect_item = inspect_map.get(full_id, {})
        repository = row["repository"]
        digest = _extract_digest(
            inspect_item.get("repo_digests", []),
            repository,
            row.get("digest"),
        )
        image_ref = _resolve_image_ref(repository, row["tag"], digest, full_id)

        images.append(
            {
                "repository": repository,
                "tag": row["tag"],
                "image_ref": image_ref,
                "image_id": _short_image_id(full_id),
                "image_id_full": full_id,
                "digest": digest,
                "created_at": inspect_item.get("created_at"),
                "size_bytes": inspect_item.get("size_bytes"),
            }
        )

    def _sort_key(item: dict[str, Any]) -> datetime:
        dt = to_orion(item.get("created_at") if isinstance(item.get("created_at"), datetime) else None)
        if dt is not None:
            return dt.astimezone(timezone.utc)
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    images.sort(key=_sort_key, reverse=True)
    if limit is None:
        return images

    bounded = max(1, min(limit, 1000))
    return images[:bounded]


async def ensure_local_image_exists(image_ref: str) -> None:
    code, out = await run_simple_command(["docker", "image", "inspect", image_ref], timeout_seconds=20)
    if code != 0:
        raise RuntimeError(out or f"image not found: {image_ref}")


async def delete_local_image(image_ref: str, force: bool = False) -> str:
    image_ref_value = image_ref.strip()
    if not image_ref_value:
        raise RuntimeError("image_ref cannot be empty")

    command = ["docker", "image", "rm"]
    if force:
        command.append("--force")
    command.append(image_ref_value)

    code, out = await run_simple_command(command, timeout_seconds=60)
    if code != 0:
        message = out or f"docker image rm failed: {image_ref_value}"
        raise RuntimeError(message)

    return out or f"image removed: {image_ref_value}"
