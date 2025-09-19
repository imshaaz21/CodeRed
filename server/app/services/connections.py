from __future__ import annotations

import asyncio
from typing import Dict, Iterable

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, player_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[player_id] = websocket

    async def disconnect(self, player_id: str) -> None:
        async with self._lock:
            websocket = self._connections.pop(player_id, None)
        if websocket is not None:
            await websocket.close()

    async def remove(self, player_id: str) -> None:
        async with self._lock:
            self._connections.pop(player_id, None)

    async def send(self, player_id: str, message: dict) -> None:
        async with self._lock:
            websocket = self._connections.get(player_id)
        if websocket is not None:
            await websocket.send_json(message)

    async def broadcast(self, player_ids: Iterable[str], message: dict) -> None:
        send_tasks = [self.send(pid, message) for pid in player_ids]
        if send_tasks:
            await asyncio.gather(*send_tasks)

    def has_connection(self, player_id: str) -> bool:
        return player_id in self._connections

    def connected_players(self) -> Iterable[str]:
        return list(self._connections.keys())
