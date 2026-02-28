from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.build import Build
from app.schemas.build import BuildCreate, BuildLogsRead, BuildRead
from app.services.build_service import create_build_if_app_exists, enqueue_build
from app.services.log_reader import read_lines_by_marker
from app.services.log_stream import log_broker

router = APIRouter(prefix="/builds", tags=["builds"])


@router.get("", response_model=list[BuildRead])
def list_builds(
    app_id: int | None = None,
    status_value: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[Build]:
    query = select(Build)
    if app_id is not None:
        query = query.where(Build.app_id == app_id)
    if status_value is not None:
        query = query.where(Build.status == status_value)
    query = query.order_by(desc(Build.id)).limit(max(1, min(limit, 500)))
    return list(db.scalars(query))


@router.post("", response_model=BuildRead, status_code=status.HTTP_202_ACCEPTED)
async def create_build(payload: BuildCreate, db: Session = Depends(get_db)) -> Build:
    try:
        build = create_build_if_app_exists(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await enqueue_build(build.id, payload)
    return build


@router.get("/{build_id}", response_model=BuildRead)
def get_build(build_id: int, db: Session = Depends(get_db)) -> Build:
    build = db.get(Build, build_id)
    if build is None:
        raise HTTPException(status_code=404, detail="Build not found")
    return build


@router.get("/{build_id}/logs", response_model=BuildLogsRead)
def get_build_logs(build_id: int, tail: int = 200, db: Session = Depends(get_db)) -> BuildLogsRead:
    build = db.get(Build, build_id)
    if build is None:
        raise HTTPException(status_code=404, detail="Build not found")
    lines = read_lines_by_marker(build.log_file, f"[BUILD_ID={build_id}]", tail=tail)
    return BuildLogsRead(build_id=build_id, lines=lines)


@router.websocket("/ws/{build_id}/logs")
async def ws_build_logs(websocket: WebSocket, build_id: int) -> None:
    await websocket.accept()
    channel = f"build:{build_id}"
    queue = await log_broker.subscribe(channel)
    try:
        while True:
            try:
                line = await asyncio.wait_for(queue.get(), timeout=60)
                await websocket.send_text(line)
            except asyncio.TimeoutError:
                await websocket.send_text("heartbeat")
    except WebSocketDisconnect:
        pass
    finally:
        await log_broker.unsubscribe(channel, queue)
