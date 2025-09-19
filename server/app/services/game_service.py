from __future__ import annotations

import asyncio
from typing import Sequence, TYPE_CHECKING

from fastapi import HTTPException

from ..models.game import Game, MoveError, Placement
from .connections import ConnectionManager
from .game_manager import GameManager

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from .bot_manager import BotManager


class GameService:
    def __init__(self, game_manager: GameManager, connections: ConnectionManager) -> None:
        self.game_manager = game_manager
        self.connections = connections
        self._bot_manager: "BotManager" | None = None

    def attach_bot_manager(self, bot_manager: "BotManager") -> None:
        self._bot_manager = bot_manager

    async def _get_game(self, game_id: str) -> Game:
        game = await self.game_manager.get_game(game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")
        return game

    def _ensure_player(self, game: Game, player_id: str) -> None:
        if player_id not in game.players:
            raise HTTPException(status_code=404, detail="Player not part of this game")

    async def submit_move(self, game_id: str, player_id: str, placements: Sequence[Placement]) -> dict:
        game = await self._get_game(game_id)
        self._ensure_player(game, player_id)
        lock = await self.game_manager.get_lock(game_id)
        async with lock:
            try:
                move_record = game.play_move(player_id, placements)
            except MoveError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            await self.push_state(game, highlight=move_record.move_type)
            return {
                "score": move_record.score,
                "words": move_record.words,
                "turn": game.current_player_id,
                "status": game.status,
            }

    async def pass_turn(self, game_id: str, player_id: str) -> dict:
        game = await self._get_game(game_id)
        self._ensure_player(game, player_id)
        lock = await self.game_manager.get_lock(game_id)
        async with lock:
            try:
                move_record = game.pass_turn(player_id)
            except MoveError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            await self.push_state(game, highlight=move_record.move_type)
            return {"status": game.status, "turn": game.current_player_id}

    async def exchange_tiles(self, game_id: str, player_id: str, letters: Sequence[str]) -> dict:
        game = await self._get_game(game_id)
        self._ensure_player(game, player_id)
        lock = await self.game_manager.get_lock(game_id)
        async with lock:
            try:
                move_record = game.exchange_tiles(player_id, letters)
            except MoveError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            await self.push_state(game, highlight=move_record.move_type)
            return {"status": game.status, "turn": game.current_player_id}

    async def refresh_state(self, game_id: str, player_id: str) -> dict:
        game = await self._get_game(game_id)
        self._ensure_player(game, player_id)
        return game.to_player_view(player_id)

    async def push_state(self, game: Game, highlight: str | None = None) -> None:
        payloads = []
        for player_id in game.player_order:
            payloads.append(
                self.connections.send(
                    player_id,
                    {
                        "type": "state",
                        "payload": game.to_player_view(player_id),
                        "highlight": highlight,
                    },
                )
            )
        if payloads:
            await asyncio.gather(*payloads)
        if game.status != "active" and self._bot_manager is not None:
            await self._bot_manager.stop(game.id)
