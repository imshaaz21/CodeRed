from __future__ import annotations

import asyncio
import contextlib
import copy
import random
import uuid
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException

from collections import Counter, defaultdict

from ..core.constants import BOARD_SIZE, CENTER_SQUARE, LETTER_SCORES
from ..core.dictionary import get_dictionary
from ..models.game import Game, MoveError, Placement
from .game_manager import GameManager
from .game_service import GameService

_BLANK_LETTER_PREFERENCES = list("AERTOINSLCDU")
_FIRST_MOVE_WORDS = ["AI", "AT", "IN", "TO", "IT", "AN"]

LEAVE_VALUES: Dict[str, float] = {
    "E": 2.5,
    "R": 2.0,
    "S": 3.0,
    "T": 1.8,
    "N": 1.6,
    "I": 1.5,
    "A": 1.2,
    "O": 1.2,
    "L": 1.1,
    "D": 1.0,
    "H": 0.8,
    "M": 0.7,
    "G": 0.6,
    "U": 0.5,
    "Y": 0.4,
    "C": 0.4,
    "B": 0.4,
    "K": 0.2,
    "F": 0.2,
    "P": 0.2,
    "V": 0.1,
    "W": 0.1,
    "X": -0.5,
    "Z": -0.5,
    "J": -0.7,
    "Q": -3.0,
}

VOWELS = {"A", "E", "I", "O", "U"}


class SimpleBotEngine:
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


class AdvancedBotEngine:
    def __init__(
        self,
        game: Game,
        bot_id: str,
        dictionary: Iterable[str],
        words_by_length: Dict[int, List[str]],
    ) -> None:
        self.game = game
        self.bot_id = bot_id
        self.player = self.game.players[bot_id]
        self.dictionary = set(dictionary)
        self.words_by_length = words_by_length
        self.board = self.game.board
        self.rack_counter = self.player.rack_counter()
        self.anchor_set = self._compute_anchors()

    def find_move(self) -> Optional[List[Placement]]:
        candidates = self._generate_candidates(limit=200)
        best_value = float("-inf")
        best_move: Optional[List[Placement]] = None
        for placements in candidates:
            trial = copy.deepcopy(self.game)
            try:
                move_record = trial.play_move(self.bot_id, placements)
            except MoveError:
                continue
            value = self._evaluate_move(move_record.score, placements)
            if value > best_value:
                best_value = value
                best_move = placements
        return best_move

    def _compute_anchors(self) -> set[tuple[int, int]]:
        anchors: set[tuple[int, int]] = set()
        if not self.board:
            anchors.add(CENTER_SQUARE)
            return anchors
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if (row, col) in self.board:
                    continue
                for d_row, d_col in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    if (row + d_row, col + d_col) in self.board:
                        anchors.add((row, col))
                        break
        return anchors

    def _generate_candidates(self, limit: int = 200) -> List[List[Placement]]:
        candidates: List[List[Placement]] = []
        if not self.anchor_set:
            return candidates
        for direction in ("horizontal", "vertical"):
            if len(candidates) >= limit:
                break
            self._scan_direction(direction, candidates, limit)
        return candidates

    def _scan_direction(self, direction: str, candidates: List[List[Placement]], limit: int) -> None:
        dr, dc = (0, 1) if direction == "horizontal" else (1, 0)
        for base in range(BOARD_SIZE):
            for start in range(BOARD_SIZE):
                row = base if direction == "horizontal" else start
                col = start if direction == "horizontal" else base
                if direction == "horizontal" and row >= BOARD_SIZE:
                    continue
                if direction == "vertical" and col >= BOARD_SIZE:
                    continue
                for length in range(1, BOARD_SIZE - start + 1):
                    if len(candidates) >= limit:
                        return
                    cells, valid = self._collect_window(row, col, dr, dc, length, direction)
                    if not valid:
                        continue
                    new_slots = sum(1 for _, _, existing in cells if existing is None)
                    if new_slots == 0:
                        continue
                    if new_slots > len(self.player.rack):
                        continue
                    words = self.words_by_length.get(length, [])
                    if not words:
                        continue
                    for word in words:
                        placements = self._build_placements(word, cells, direction)
                        if placements:
                            candidates.append(placements)
                            if len(candidates) >= limit:
                                return

    def _collect_window(
        self,
        row: int,
        col: int,
        dr: int,
        dc: int,
        length: int,
        direction: str,
    ) -> tuple[List[tuple[int, int, Optional[str]]], bool]:
        cells: List[tuple[int, int, Optional[str]]] = []
        anchors_touched = False
        existing_tiles = False
        for offset in range(length):
            r = row + dr * offset
            c = col + dc * offset
            if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
                return [], False
            tile = self.board.get((r, c))
            if tile:
                existing_tiles = True
                cells.append((r, c, tile.letter))
            else:
                cells.append((r, c, None))
                if (r, c) in self.anchor_set:
                    anchors_touched = True
        if not self.board:
            if CENTER_SQUARE not in {(r, c) for r, c, _ in cells}:
                return [], False
            anchors_touched = True
        else:
            if not anchors_touched:
                return [], False
        # Ensure word is not connected to existing tiles just outside window
        prev_r = row - dr
        prev_c = col - dc
        if 0 <= prev_r < BOARD_SIZE and 0 <= prev_c < BOARD_SIZE:
            if (prev_r, prev_c) in self.board:
                return [], False
        end_r = row + dr * length
        end_c = col + dc * length
        if 0 <= end_r < BOARD_SIZE and 0 <= end_c < BOARD_SIZE:
            if (end_r, end_c) in self.board:
                return [], False
        return cells, True

    def _build_placements(
        self,
        word: str,
        cells: List[tuple[int, int, Optional[str]]],
        direction: str,
    ) -> Optional[List[Placement]]:
        rack_counter = Counter(self.rack_counter)
        temp_letters: Dict[tuple[int, int], str] = {}
        placements: List[Placement] = []
        used_new = False
        for idx, (row, col, existing_letter) in enumerate(cells):
            target_letter = word[idx]
            if existing_letter:
                if existing_letter != target_letter:
                    return None
                continue
            used_new = True
            is_blank = False
            if rack_counter[target_letter] > 0:
                rack_counter[target_letter] -= 1
            elif rack_counter["?"] > 0:
                rack_counter["?"] -= 1
                is_blank = True
            else:
                return None
            if not self._cross_check(row, col, target_letter, temp_letters, direction):
                return None
            placements.append(Placement(row=row, col=col, letter=target_letter, is_blank=is_blank))
            temp_letters[(row, col)] = target_letter
        if not used_new:
            return None
        return placements

    def _cross_check(
        self,
        row: int,
        col: int,
        letter: str,
        temp_letters: Dict[tuple[int, int], str],
        direction: str,
    ) -> bool:
        if not self.board:
            return True
        delta = (-1, 0) if direction == "horizontal" else (0, -1)
        reverse_delta = (1, 0) if direction == "horizontal" else (0, 1)
        backward_letters: List[str] = []
        r, c = row + delta[0], col + delta[1]
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            ch = self._letter_at(r, c, temp_letters)
            if not ch:
                break
            backward_letters.insert(0, ch)
            r += delta[0]
            c += delta[1]
        forward_letters: List[str] = []
        r, c = row + reverse_delta[0], col + reverse_delta[1]
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            ch = self._letter_at(r, c, temp_letters)
            if not ch:
                break
            forward_letters.append(ch)
            r += reverse_delta[0]
            c += reverse_delta[1]
        word_letters = backward_letters + [letter] + forward_letters
        if len(word_letters) <= 1:
            return True
        candidate = "".join(word_letters)
        return candidate in self.dictionary

    def _letter_at(self, row: int, col: int, temp_letters: Dict[tuple[int, int], str]) -> Optional[str]:
        if (row, col) in temp_letters:
            return temp_letters[(row, col)]
        tile = self.board.get((row, col))
        if tile:
            return tile.letter
        return None

    def _evaluate_move(self, score: int, placements: List[Placement]) -> float:
        leftover = Counter(self.rack_counter)
        for placement in placements:
            key = "?" if placement.is_blank else placement.letter
            leftover[key] -= 1
            if leftover[key] <= 0:
                leftover.pop(key, None)
        leave_score = self._leave_value(leftover)
        move_value = score + leave_score
        if len(placements) >= 6:
            move_value += 10
        return move_value

    def _leave_value(self, leftover: Counter) -> float:
        value = 0.0
        vowel_count = 0
        consonant_count = 0
        for letter, count in leftover.items():
            if count <= 0:
                continue
            if letter == "?":
                value += 1.0 * count
                continue
            value += LEAVE_VALUES.get(letter, 0.0) * count
            if letter in VOWELS:
                vowel_count += count
            else:
                consonant_count += count
        if vowel_count == 0 and consonant_count > 0:
            value -= 3
        if consonant_count == 0 and vowel_count > 0:
            value -= 3
        if abs(vowel_count - consonant_count) <= 1:
            value += 2
        if leftover.get("Q", 0) > 0 and leftover.get("U", 0) == 0:
            value -= 8
        return value

class BotManager:
    def __init__(self, game_manager: GameManager, game_service: GameService) -> None:
        self.game_manager = game_manager
        self.game_service = game_service
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        dictionary = get_dictionary()
        self.dictionary = dictionary
        words_by_length: Dict[int, List[str]] = defaultdict(list)
        for word in dictionary:
            if 0 < len(word) <= BOARD_SIZE:
                words_by_length[len(word)].append(word)
        self.words_by_length = {length: words for length, words in words_by_length.items()}

    async def create_bot_game(
        self,
        human_id: str,
        human_name: str,
        bot_display_name: str,
    ) -> tuple[Game, str]:
        bot_id = f"bot-{uuid.uuid4().hex}"
        game = await self.game_manager.create_game(
            [
                (human_id, human_name),
                (bot_id, bot_display_name),
            ]
        )
        return game, bot_id

    async def start(self, game_id: str, bot_id: str, *, strategy: str = "basic") -> None:
        async with self._lock:
            if game_id in self._tasks:
                return
            task = asyncio.create_task(self._run_bot(game_id, bot_id, strategy))
            self._tasks[game_id] = task

    async def stop(self, game_id: str) -> None:
        async with self._lock:
            task = self._tasks.pop(game_id, None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run_bot(self, game_id: str, bot_id: str, strategy: str) -> None:
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
                        if strategy == "advanced":
                            engine = AdvancedBotEngine(
                                game,
                                bot_id,
                                self.dictionary,
                                self.words_by_length,
                            )
                            placements = engine.find_move()
                            if placements is None:
                                placements = SimpleBotEngine(game, bot_id).find_move()
                        else:
                            engine = SimpleBotEngine(game, bot_id)
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
