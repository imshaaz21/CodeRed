from __future__ import annotations

import asyncio
import uuid
from typing import Dict, Iterable, Optional, Sequence, Tuple

from ..models.game import Game


class GameManager:
    def __init__(self) -> None:
        self._games: Dict[str, Game] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._player_to_game: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create_game(self, players: Sequence[Tuple[str, str]]) -> Game:
        game_id = uuid.uuid4().hex
        game = Game(game_id, players)
        async with self._lock:
            self._games[game_id] = game
            self._locks[game_id] = asyncio.Lock()
            for player_id, _ in players:
                self._player_to_game[player_id] = game_id
        return game

    async def get_game(self, game_id: str) -> Optional[Game]:
        async with self._lock:
            return self._games.get(game_id)

    async def get_game_for_player(self, player_id: str) -> Optional[Game]:
        async with self._lock:
            game_id = self._player_to_game.get(player_id)
        if not game_id:
            return None
        return await self.get_game(game_id)

    async def get_lock(self, game_id: str) -> asyncio.Lock:
        async with self._lock:
            lock = self._locks.get(game_id)
            if lock is None:
                raise KeyError(f"Unknown game {game_id}")
            return lock

    async def remove_game(self, game_id: str) -> None:
        async with self._lock:
            game = self._games.pop(game_id, None)
            self._locks.pop(game_id, None)
            if game:
                for player_id in game.player_order:
                    self._player_to_game.pop(player_id, None)

    async def active_games(self) -> Iterable[Game]:
        async with self._lock:
            return list(self._games.values())
