from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class JoinLobbyRequest(BaseModel):
    displayName: Optional[str] = Field(default=None, max_length=20)
    mode: Literal["multi", "bot", "bot-advanced"] = "multi"


class JoinLobbyResponse(BaseModel):
    playerId: str


class PlacementPayload(BaseModel):
    row: int
    col: int
    letter: str
    isBlank: bool = False


class MoveRequest(BaseModel):
    playerId: str
    placements: List[PlacementPayload]


class PassRequest(BaseModel):
    playerId: str


class ExchangeRequest(BaseModel):
    playerId: str
    letters: List[str]
