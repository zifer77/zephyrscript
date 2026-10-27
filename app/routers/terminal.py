import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import SessionLocal
from app.models.project import Project
from app.services import file_service, terminal_service
from app.services.auth_service import user_from_token

router = APIRouter(tags=["terminal"])


@router.websocket("/ws/terminal")
async def terminal_ws(ws: WebSocket, token: str = Query(""), project_id: int = Query(...)):
    """
    Protokol:
      client -> server : teks mentah (keystroke) ATAU JSON
                         {"type":"input","data":"ls\\n"} / {"type":"resize","cols":80,"rows":24}
      server -> client : teks output shell (stream)
    Close code: 4401 = auth gagal, 4404 = project tidak ada, 4429 = terlalu banyak terminal.
    """
    await ws.accept()

    db = SessionLocal()
    try:
        user = user_from_token(db, token)
        if not user:
            await ws.close(code=4401, reason="Unauthorized")
            return
        project = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
        if not project:
            await ws.close(code=4404, reason="Project not found")
            return
        user_id, pid = user.id, project.id
    finally:
        db.close()

    if not terminal_service.acquire(user_id, settings.max_terminals_per_user):
        await ws.close(code=4429, reason="Too many terminals")
        return

    session = terminal_service.TerminalSession(file_service.project_dir(pid), settings.terminal_shell)
    try:
        session.start()
    except Exception as e:  # shell tidak ditemukan, dll.
        terminal_service.release(user_id)
        await ws.send_text(f"\r\n[gagal menjalankan shell: {e}]\r\n")
        await ws.close(code=1011)
        return

    async def pump_output() -> None:
        while True:
            data = await session.queue.get()
            if data is None:
                await ws.send_text("\r\n[shell selesai]\r\n")
                await ws.close(code=1000)
                return
            text = session.decode(data)
            if text:
                await ws.send_text(text)

    out_task = asyncio.create_task(pump_output())
    try:
        while True:
            msg = await ws.receive_text()
            if msg.startswith("{"):
                try:
                    obj = json.loads(msg)
                except ValueError:
                    obj = None
                if isinstance(obj, dict) and obj.get("type") == "resize":
                    session.resize(obj.get("cols", 80), obj.get("rows", 24))
                    continue
                if isinstance(obj, dict) and obj.get("type") == "input":
                    session.write(str(obj.get("data", "")))
                    continue
            session.write(msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        out_task.cancel()
        await session.close()  # kill shell + semua child
        terminal_service.release(user_id)
