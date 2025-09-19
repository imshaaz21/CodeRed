from __future__ import annotations

from fastapi import APIRouter

from ..models.game import Placement
from ..services.bot_manager import BotManager
from ..services.clock_manager import ClockManager
from ..services.connections import ConnectionManager
from ..services.game_manager import GameManager
from ..services.game_service import GameService
from ..services.lobby_manager import LobbyManager
from .schemas import (
    ExchangeRequest,
    JoinLobbyRequest,
    JoinLobbyResponse,
    MoveRequest,
    PassRequest,
)

router = APIRouter(prefix="/api")

connections = ConnectionManager()
game_manager = GameManager()
game_service = GameService(game_manager, connections)
clock_manager = ClockManager(game_manager, game_service)
bot_manager = BotManager(game_manager, game_service)
lobby_manager = LobbyManager(connections, game_manager, clock_manager, bot_manager)


@router.post("/lobby/join", response_model=JoinLobbyResponse)
async def join_lobby(payload: JoinLobbyRequest | None = None) -> JoinLobbyResponse:
    display_name = payload.displayName if payload else None
    mode = payload.mode if payload else "multi"
    entry = await lobby_manager.create_player(display_name, mode)
    return JoinLobbyResponse(playerId=entry.player_id)


@router.post("/game/{game_id}/move")
async def submit_move(game_id: str, request: MoveRequest):
    placements = [
        Placement(row=item.row, col=item.col, letter=item.letter, is_blank=item.isBlank)
        for item in request.placements
    ]
    return await game_service.submit_move(game_id, request.playerId, placements)


@router.post("/game/{game_id}/pass")
async def pass_turn(game_id: str, request: PassRequest):
    return await game_service.pass_turn(game_id, request.playerId)


@router.post("/game/{game_id}/exchange")
async def exchange_tiles(game_id: str, request: ExchangeRequest):
    return await game_service.exchange_tiles(game_id, request.playerId, request.letters)


@router.get("/game/{game_id}/state")
async def get_state(game_id: str, playerId: str):
    return await game_service.refresh_state(game_id, playerId)
