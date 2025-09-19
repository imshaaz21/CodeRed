from __future__ import annotations

import asyncio
import contextlib
import copy
import random
import uuid
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException

from ..core.constants import BOARD_SIZE, CENTER_SQUARE
from ..models.game import Game, MoveError, Placement
from .game_manager import GameManager
from .game_service import GameService

_BLANK_LETTER_PREFERENCES = list("AERTOINSLCDU")
_FIRST_MOVE_WORDS = ["AI", "AT", "IN", "TO", "IT", "AN"]


class BotEngine:
    def __init__(self, game: Game, bot_id: str) -> None:
        self.game = game
        self.bot_id = bot_id
        self.player = self.game.players[bot_id]
        self.dictionary = self.game.dictionary

    def find_move(self) -> Optional[List[Placement]]:
        if not self.game.board:
            move = self._first_move()
            if move:
                return move
        move = self._adjacent_single_tile_move()
        if move:
            return move
        return None

    def _first_move(self) -> Optional[List[Placement]]:
        center_row, center_col = CENTER_SQUARE
        # Single-letter words first
        for letter, is_blank in self._iter_rack_letters():
            if self._test_move([Placement(row=center_row, col=center_col, letter=letter, is_blank=is_blank)]):
                return [Placement(row=center_row, col=center_col, letter=letter, is_blank=is_blank)]
        # Try simple two-letter words across center
        for word in _FIRST_MOVE_WORDS:
            placements = self._try_first_move_word(word)
            if placements:
                return placements
        return None

    def _try_first_move_word(self, word: str) -> Optional[List[Placement]]:
        center_row, center_col = CENTER_SQUARE
        half = len(word) // 2
        start_col = center_col - half
        placements: List[Placement] = []
        used_indices: List[int] = []
        for offset, target_col in enumerate(range(start_col, start_col + len(word))):
            target_letter = word[offset]
            rack_index, is_blank = self._take_tile(target_letter, used_indices)
            if rack_index is None:
                return None
            used_indices.append(rack_index)
            placements.append(
                Placement(row=center_row, col=target_col, letter=target_letter, is_blank=is_blank)
            )
        if self._test_move(placements):
            return placements
        return None

    def _adjacent_single_tile_move(self) -> Optional[List[Placement]]:
        board_coords = list(self.game.board.keys())
        random.shuffle(board_coords)
        for row, col in board_coords:
            neighbors = [
                (row, col - 1),
                (row, col + 1),
                (row - 1, col),
                (row + 1, col),
            ]
            for n_row, n_col in neighbors:
                if (n_row, n_col) in self.game.board:
                    continue
                if not (0 <= n_row < BOARD_SIZE and 0 <= n_col < BOARD_SIZE):
                    continue
                for letter, is_blank in self._iter_rack_letters():
                    placement = Placement(row=n_row, col=n_col, letter=letter, is_blank=is_blank)
                    if self._test_move([placement]):
                        return [placement]
        return None

    def _iter_rack_letters(self) -> Iterable[tuple[str, bool]]:
        rack_letters: List[tuple[str, bool]] = []
        for tile in self.player.rack:
            if tile.is_blank:
                for candidate in _BLANK_LETTER_PREFERENCES:
                    rack_letters.append((candidate, True))
            else:
                rack_letters.append((tile.letter, False))
        random.shuffle(rack_letters)
        return rack_letters

    def _take_tile(self, target: str, used_indices: List[int]) -> tuple[Optional[int], bool]:
        for idx, tile in enumerate(self.player.rack):
            if idx in used_indices:
                continue
            if tile.is_blank:
                return idx, True
            if tile.letter == target:
                return idx, False
        return None, False

    def _test_move(self, placements: List[Placement]) -> bool:
        trial = copy.deepcopy(self.game)
        try:
            trial.play_move(self.bot_id, placements)
        except MoveError:
            return False
        return True


class BotManager:
    def __init__(self, game_manager: GameManager, game_service: GameService) -> None:
        self.game_manager = game_manager
        self.game_service = game_service
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def create_bot_game(self, human_id: str, human_name: str) -> tuple[Game, str]:
        bot_id = f"bot-{uuid.uuid4().hex}"
        bot_name = "Bot"
        game = await self.game_manager.create_game(
            [
                (human_id, human_name),
                (bot_id, bot_name),
            ]
        )
        return game, bot_id

    async def start(self, game_id: str, bot_id: str) -> None:
        async with self._lock:
            if game_id in self._tasks:
                return
            task = asyncio.create_task(self._run_bot(game_id, bot_id))
            self._tasks[game_id] = task

    async def stop(self, game_id: str) -> None:
        async with self._lock:
            task = self._tasks.pop(game_id, None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run_bot(self, game_id: str, bot_id: str) -> None:
        try:
            while True:
                game = await self.game_manager.get_game(game_id)
                if game is None:
                    return

                lock = await self.game_manager.get_lock(game_id)
                should_move = False
                placements: Optional[List[Placement]] = None
                status = game.status
                async with lock:
                    if game.status != "active":
                        break
                    if game.current_player_id != bot_id:
                        status = game.status
                    else:
                        engine = BotEngine(game, bot_id)
                        placements = engine.find_move()
                        should_move = True
                        status = game.status

                if not should_move:
                    if status != "active":
                        break
                    await asyncio.sleep(0.5)
                    continue

                try:
                    if placements:
                        await self.game_service.submit_move(game_id, bot_id, placements)
                    else:
                        await self.game_service.pass_turn(game_id, bot_id)
                except HTTPException:
                    await asyncio.sleep(1.0)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return
        finally:
            async with self._lock:
                existing = self._tasks.get(game_id)
                if existing is asyncio.current_task():
                    self._tasks.pop(game_id, None)
