from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class JoinLobbyRequest(BaseModel):
    displayName: Optional[str] = Field(default=None, max_length=20)


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
