import json
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ws/coding", tags=["Coding WebSocket"])


class CodingConnectionManager:
    def __init__(self):
        # Maps interview_id to set of candidate sockets
        self.candidate_connections: Dict[str, WebSocket] = {}
        # Maps interview_id to set of admin monitoring sockets
        self.admin_connections: Dict[str, Set[WebSocket]] = {}

    async def connect_candidate(self, interview_id: str, websocket: WebSocket):
        await websocket.accept()
        self.candidate_connections[interview_id] = websocket

    def disconnect_candidate(self, interview_id: str):
        if interview_id in self.candidate_connections:
            del self.candidate_connections[interview_id]

    async def connect_admin(self, interview_id: str, websocket: WebSocket):
        await websocket.accept()
        if interview_id not in self.admin_connections:
            self.admin_connections[interview_id] = set()
        self.admin_connections[interview_id].add(websocket)

    def disconnect_admin(self, interview_id: str, websocket: WebSocket):
        if interview_id in self.admin_connections:
            self.admin_connections[interview_id].discard(websocket)
            if not self.admin_connections[interview_id]:
                del self.admin_connections[interview_id]

    async def broadcast_to_admins(self, interview_id: str, message: dict):
        if interview_id in self.admin_connections:
            dead_sockets = set()
            for ws in self.admin_connections[interview_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_sockets.add(ws)
            for ds in dead_sockets:
                self.admin_connections[interview_id].discard(ds)


manager = CodingConnectionManager()


@router.websocket("/session/{interview_id}")
async def coding_candidate_websocket(websocket: WebSocket, interview_id: str):
    """Candidate live keystroke & proctoring event sync socket."""
    await manager.connect_candidate(interview_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                # Broadcast keystroke / code change / proctor event to listening admin dashboards
                await manager.broadcast_to_admins(interview_id, payload)
            except Exception as e:
                logger.warning("coding_ws_payload_parse_error", error=str(e))
    except WebSocketDisconnect:
        manager.disconnect_candidate(interview_id)
        await manager.broadcast_to_admins(interview_id, {"type": "CANDIDATE_DISCONNECTED", "interview_id": interview_id})


@router.websocket("/monitor/{interview_id}")
async def coding_admin_websocket(websocket: WebSocket, interview_id: str):
    """Admin live monitoring socket to view real-time code changes & proctor alerts."""
    await manager.connect_admin(interview_id, websocket)
    try:
        while True:
            # Admins listen passively
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_admin(interview_id, websocket)
