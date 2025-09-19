from __future__ import annotations

import asyncio
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional

from .clock_manager import ClockManager
from .connections import ConnectionManager
from .game_manager import GameManager


@dataclass
class LobbyEntry:
    player_id: str
    display_name: str
    connected: bool = False


class LobbyManager:
    def __init__(self, connection_manager: ConnectionManager, game_manager: GameManager, clock_manager: ClockManager) -> None:
        self.connection_manager = connection_manager
        self.game_manager = game_manager
        self.clock_manager = clock_manager
        self._waiting: Deque[LobbyEntry] = deque()
        self._entries: Dict[str, LobbyEntry] = {}
        self._lock = asyncio.Lock()

    async def create_player(self, display_name: Optional[str] = None) -> LobbyEntry:
        player_id = uuid.uuid4().hex
        fallback_name = f"Player-{player_id[:4]}"
        name = (display_name or fallback_name)[:20]
        entry = LobbyEntry(player_id=player_id, display_name=name or fallback_name)
        async with self._lock:
            self._waiting.append(entry)
            self._entries[player_id] = entry
        return entry

    async def mark_connected(self, player_id: str) -> None:
        async with self._lock:
            entry = self._entries.get(player_id)
            if entry:
                entry.connected = True
        await self._try_match()

    async def leave(self, player_id: str) -> None:
        async with self._lock:
            entry = self._entries.pop(player_id, None)
            if entry and entry in self._waiting:
                self._waiting.remove(entry)
        await self.connection_manager.remove(player_id)

    async def _try_match(self) -> None:
        pairs = []
        async with self._lock:
            ready = [entry for entry in self._waiting if entry.connected]
            while len(ready) >= 2:
                first = ready.pop(0)
                second = ready.pop(0)
                self._waiting.remove(first)
                self._waiting.remove(second)
                self._entries.pop(first.player_id, None)
                self._entries.pop(second.player_id, None)
                pairs.append((first, second))
        for first, second in pairs:
            game = await self.game_manager.create_game(
                [
                    (first.player_id, first.display_name),
                    (second.player_id, second.display_name),
                ]
            )
            await self.clock_manager.start(game.id)
            await self.connection_manager.broadcast(
                [first.player_id, second.player_id],
                {
                    "type": "match_found",
                    "gameId": game.id,
                    "players": [
                        {"playerId": pid, "displayName": game.players[pid].display_name}
                        for pid in game.player_order
                    ],
                    "yourTurn": game.current_player_id,
                },
            )
            await self._send_state(game)

    async def _send_state(self, game) -> None:
        for player_id in game.player_order:
            if self.connection_manager.has_connection(player_id):
                await self.connection_manager.send(
                    player_id,
                    {"type": "state", "payload": game.to_player_view(player_id)},
                )
