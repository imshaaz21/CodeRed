from __future__ import annotations

import random
import string
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..core.constants import (
    BOARD_SIZE,
    CENTER_SQUARE,
    LETTER_DISTRIBUTION,
    LETTER_SCORES,
    PREMIUM_SQUARES,
)
from ..core.dictionary import get_dictionary

Coordinate = Tuple[int, int]

TURN_TIME_LIMIT_SECONDS = 10 * 60


@dataclass
class Tile:
    letter: str
    is_blank: bool = False

    @property
    def score(self) -> int:
        return LETTER_SCORES[self.letter if not self.is_blank else "?"]


@dataclass
class BoardTile:
    letter: str
    is_blank: bool
    placed_by: str
    turn_played: int

    @property
    def score(self) -> int:
        return 0 if self.is_blank else LETTER_SCORES[self.letter]


@dataclass
class PlayerState:
    player_id: str
    display_name: str
    rack: List[Tile] = field(default_factory=list)
    score: int = 0

    def rack_counter(self) -> Counter[str]:
        return Counter(tile.letter if not tile.is_blank else "?" for tile in self.rack)


@dataclass
class Placement:
    row: int
    col: int
    letter: str
    is_blank: bool = False

    @property
    def coordinate(self) -> Coordinate:
        return self.row, self.col


@dataclass
class MoveRecord:
    turn_number: int
    player_id: str
    move_type: str
    placements: List[Placement]
    score: int
    words: List[str]
    exchanged: List[str] = field(default_factory=list)


class MoveError(Exception):
    """Raised when a player attempts an illegal move."""


class Game:
    def __init__(self, game_id: str, players: Sequence[Tuple[str, str]], *, dictionary_path: Optional[str] = None) -> None:
        if len(players) != 2:
            raise ValueError("A game requires exactly two players")

        self.id = game_id
        self.created_at = datetime.utcnow()
        self.dictionary = get_dictionary(dictionary_path)
        self.board: Dict[Coordinate, BoardTile] = {}
        self.tile_bag: List[Tile] = self._build_initial_bag()
        random.shuffle(self.tile_bag)

        shuffled_players = list(players)
        random.shuffle(shuffled_players)
        self.player_order: List[str] = [player_id for player_id, _ in shuffled_players]
        self.players: Dict[str, PlayerState] = {
            player_id: PlayerState(player_id=player_id, display_name=name)
            for player_id, name in shuffled_players
        }
        self.turn_index = 0
        self.turn_number = 1
        self.status: str = "active"
        self.passes_in_a_row = 0
        self.clock_remaining: Dict[str, float] = {
            player_id: float(TURN_TIME_LIMIT_SECONDS)
            for player_id in self.player_order
        }
        self.turn_started_at: datetime = datetime.utcnow()
        self.result: Optional[Dict[str, str]] = None

        for player in self.players.values():
            self._draw_tiles(player, limit=7)

        self.move_history: List[MoveRecord] = []

    # ------------------------------------------------------------------
    # Tile bag helpers
    # ------------------------------------------------------------------
    def _build_initial_bag(self) -> List[Tile]:
        bag: List[Tile] = []
        for letter, count in LETTER_DISTRIBUTION.items():
            if letter == "?":
                bag.extend([Tile(letter="?", is_blank=True) for _ in range(count)])
            else:
                bag.extend([Tile(letter=letter) for _ in range(count)])
        return bag

    def _draw_tiles(self, player: PlayerState, limit: int = 7) -> None:
        needed = limit - len(player.rack)
        for _ in range(min(needed, len(self.tile_bag))):
            player.rack.append(self.tile_bag.pop())

    def _sync_active_clock(self, *, now: Optional[datetime] = None) -> bool:
        if self.status != "active":
            return False
        now = now or datetime.utcnow()
        elapsed = (now - self.turn_started_at).total_seconds()
        if elapsed <= 0:
            return False
        current_player = self.current_player_id
        remaining = max(0.0, self.clock_remaining[current_player] - elapsed)
        clock_changed = abs(remaining - self.clock_remaining[current_player]) > 1e-6
        self.clock_remaining[current_player] = remaining
        self.turn_started_at = now
        if remaining <= 0:
            self._handle_timeout(current_player)
            clock_changed = True
        return clock_changed

    def sync_clock(self, *, now: Optional[datetime] = None) -> bool:
        return self._sync_active_clock(now=now)

    def _handle_timeout(self, timed_out_player: str) -> None:
        if self.status != "active":
            return
        opponent_id = next(pid for pid in self.player_order if pid != timed_out_player)
        self.status = "completed"
        self.result = {
            "winner": opponent_id,
            "loser": timed_out_player,
            "reason": "timeout",
        }
        self.move_history.append(
            MoveRecord(
                turn_number=self.turn_number,
                player_id=timed_out_player,
                move_type="timeout",
                placements=[],
                score=0,
                words=[],
            )
        )

    def _clock_snapshot(self, *, now: Optional[datetime] = None) -> Dict[str, float]:
        snapshot = {player_id: max(0.0, remaining) for player_id, remaining in self.clock_remaining.items()}
        if self.status == "active":
            reference = now or datetime.utcnow()
            elapsed = (reference - self.turn_started_at).total_seconds()
            if elapsed > 0:
                current_player = self.current_player_id
                snapshot[current_player] = max(0.0, snapshot[current_player] - elapsed)
        return snapshot

    # ------------------------------------------------------------------
    # Turn helpers
    # ------------------------------------------------------------------
    @property
    def current_player_id(self) -> str:
        return self.player_order[self.turn_index]

    def _advance_turn(self) -> None:
        self.turn_index = (self.turn_index + 1) % len(self.player_order)
        self.turn_number += 1
        if self.status == "active":
            self.turn_started_at = datetime.utcnow()

    # ------------------------------------------------------------------
    # Move execution
    # ------------------------------------------------------------------
    def play_move(self, player_id: str, placements: Sequence[Placement]) -> MoveRecord:
        self._sync_active_clock()
        if self.status != "active":
            raise MoveError("Game is not active")
        if player_id != self.current_player_id:
            raise MoveError("It is not your turn")
        if not placements:
            raise MoveError("No tiles placed")

        player = self.players[player_id]
        normalized = [self._normalize_placement(p) for p in placements]
        placement_map = {p.coordinate: p for p in normalized}

        self._validate_placements(player, placement_map)
        words, total_score = self._evaluate_move(player_id, placement_map)

        self._apply_placements(player_id, placement_map)
        player.score += total_score
        self._draw_tiles(player, limit=7)

        self.passes_in_a_row = 0

        move_record = MoveRecord(
            turn_number=self.turn_number,
            player_id=player_id,
            move_type="play",
            placements=list(placement_map.values()),
            score=total_score,
            words=words,
        )
        self.move_history.append(move_record)

        self._advance_turn()
        self._check_game_end()

        return move_record

    def pass_turn(self, player_id: str) -> MoveRecord:
        self._sync_active_clock()
        if self.status != "active":
            raise MoveError("Game is not active")
        if player_id != self.current_player_id:
            raise MoveError("It is not your turn")

        self.passes_in_a_row += 1
        move_record = MoveRecord(
            turn_number=self.turn_number,
            player_id=player_id,
            move_type="pass",
            placements=[],
            score=0,
            words=[],
        )
        self.move_history.append(move_record)

        self._advance_turn()
        if self.passes_in_a_row >= 6:
            self.status = "completed"
            self._finalize_scores("consecutive passes")
        return move_record

    def exchange_tiles(self, player_id: str, letters: Sequence[str]) -> MoveRecord:
        self._sync_active_clock()
        if self.status != "active":
            raise MoveError("Game is not active")
        if player_id != self.current_player_id:
            raise MoveError("It is not your turn")
        if len(self.tile_bag) < len(letters):
            raise MoveError("Not enough tiles in the bag to exchange")
        if not letters:
            raise MoveError("No tiles selected for exchange")

        player = self.players[player_id]
        rack_counter = player.rack_counter()
        for raw_letter in letters:
            letter = raw_letter.upper()
            if letter not in string.ascii_uppercase and letter != "?":
                raise MoveError(f"Invalid tile letter {raw_letter}")
            key = letter if letter in rack_counter else ("?" if letter != "?" else letter)
            if rack_counter[key] <= 0:
                raise MoveError(f"Tile {raw_letter} not in rack")
            rack_counter[key] -= 1

        exchanged_tiles: List[Tile] = []
        # Remove selected tiles from rack
        for letter in letters:
            normalized = letter.upper()
            for idx, tile in enumerate(player.rack):
                tile_key = tile.letter if not tile.is_blank else "?"
                if tile_key == normalized or (tile.is_blank and normalized != "?" and tile_key == "?"):
                    exchanged_tiles.append(player.rack.pop(idx))
                    break

        # Return to bag, reshuffle for fairness
        self.tile_bag.extend(exchanged_tiles)
        random.shuffle(self.tile_bag)

        # Draw replacements
        self._draw_tiles(player, limit=7)

        self.passes_in_a_row += 1
        move_record = MoveRecord(
            turn_number=self.turn_number,
            player_id=player_id,
            move_type="exchange",
            placements=[],
            score=0,
            words=[],
            exchanged=[tile.letter if not tile.is_blank else "?" for tile in exchanged_tiles],
        )
        self.move_history.append(move_record)

        self._advance_turn()
        if self.passes_in_a_row >= 6:
            self.status = "completed"
            self._finalize_scores("consecutive passes")
        return move_record

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    def _normalize_placement(self, placement: Placement) -> Placement:
        letter = placement.letter.upper()
        if letter == "?":
            raise MoveError("Blank tiles must be assigned a letter")
        if placement.is_blank and letter not in string.ascii_uppercase:
            raise MoveError("Blank tile assignment must be A-Z")
        if not placement.is_blank and letter not in string.ascii_uppercase:
            raise MoveError("Tiles must be A-Z")
        if not (0 <= placement.row < BOARD_SIZE and 0 <= placement.col < BOARD_SIZE):
            raise MoveError("Placement outside of board bounds")
        return Placement(row=placement.row, col=placement.col, letter=letter, is_blank=placement.is_blank)

    def _validate_placements(self, player: PlayerState, placement_map: Dict[Coordinate, Placement]) -> None:
        # Check for duplicate coordinates
        if len(placement_map) != len(set(placement_map.keys())):
            raise MoveError("Duplicate tile placements")

        # All squares must be empty
        for coord in placement_map:
            if coord in self.board:
                raise MoveError("Cannot place on an occupied square")

        rack_counter = player.rack_counter()
        for placement in placement_map.values():
            key = placement.letter if not placement.is_blank else "?"
            if rack_counter[key] <= 0:
                # For blanks, allow assignment if there is blank tile
                raise MoveError(f"Tile {placement.letter} not available in rack")
            rack_counter[key] -= 1

        rows = {placement.row for placement in placement_map.values()}
        cols = {placement.col for placement in placement_map.values()}
        if len(rows) > 1 and len(cols) > 1:
            raise MoveError("Tiles must be in a single row or column")

        if not self.board and CENTER_SQUARE not in placement_map:
            raise MoveError("First move must cover the center square")

        if not self.board and len(placement_map) == 0:
            raise MoveError("First move must place tiles")

        if self.board:
            # Ensure new tiles touch existing ones
            if not any(self._has_adjacent_existing(coord) for coord in placement_map):
                raise MoveError("New tiles must connect to existing words")

        # Ensure contiguous along the direction of play
        direction = "horizontal" if len(rows) == 1 else "vertical"
        sorted_coords = sorted(placement_map.keys())
        if direction == "horizontal":
            row = next(iter(rows))
            min_col = min(cols)
            max_col = max(cols)
            for col in range(min_col, max_col + 1):
                if (row, col) not in placement_map and (row, col) not in self.board:
                    raise MoveError("Words must be contiguous")
        else:
            col = next(iter(cols))
            min_row = min(rows)
            max_row = max(rows)
            for row in range(min_row, max_row + 1):
                if (row, col) not in placement_map and (row, col) not in self.board:
                    raise MoveError("Words must be contiguous")

    def _has_adjacent_existing(self, coord: Coordinate) -> bool:
        row, col = coord
        neighbors = [
            (row - 1, col),
            (row + 1, col),
            (row, col - 1),
            (row, col + 1),
        ]
        for n_row, n_col in neighbors:
            if 0 <= n_row < BOARD_SIZE and 0 <= n_col < BOARD_SIZE and (n_row, n_col) in self.board:
                return True
        return False

    # ------------------------------------------------------------------
    # Move evaluation and application
    # ------------------------------------------------------------------
    def _evaluate_move(self, player_id: str, placement_map: Dict[Coordinate, Placement]) -> Tuple[List[str], int]:
        words: List[str] = []
        total_score = 0

        direction = self._infer_direction(placement_map)
        main_word_coords = self._collect_word_coordinates(next(iter(placement_map)), placement_map, direction)
        main_word = self._build_word(main_word_coords, placement_map)
        self._validate_word(main_word)
        words.append(main_word)
        total_score += self._score_word(main_word_coords, placement_map)

        perpendicular = "vertical" if direction == "horizontal" else "horizontal"
        for coord in placement_map:
            cross_coords = self._collect_word_coordinates(coord, placement_map, perpendicular)
            if len(cross_coords) > 1:
                word = self._build_word(cross_coords, placement_map)
                self._validate_word(word)
                words.append(word)
                total_score += self._score_word(cross_coords, placement_map)

        return words, total_score

    def _infer_direction(self, placement_map: Dict[Coordinate, Placement]) -> str:
        rows = {p.row for p in placement_map.values()}
        cols = {p.col for p in placement_map.values()}
        if len(placement_map) == 1:
            # Single tile move: check surroundings to determine direction preference
            coord = next(iter(placement_map.keys()))
            row, col = coord
            # If there are neighbors horizontally, prefer horizontal
            if (row, col - 1) in self.board or (row, col + 1) in self.board:
                return "horizontal"
            if (row - 1, col) in self.board or (row + 1, col) in self.board:
                return "vertical"
            # Default horizontal for single-tile first placement
            return "horizontal"
        if len(rows) == 1:
            return "horizontal"
        return "vertical"

    def _collect_word_coordinates(
        self,
        origin: Coordinate,
        placement_map: Dict[Coordinate, Placement],
        direction: str,
    ) -> List[Coordinate]:
        dr, dc = (0, 1) if direction == "horizontal" else (1, 0)
        row, col = origin

        # Move backwards to find start
        start_row, start_col = row, col
        while True:
            prev_row = start_row - dr
            prev_col = start_col - dc
            if not (0 <= prev_row < BOARD_SIZE and 0 <= prev_col < BOARD_SIZE):
                break
            if (prev_row, prev_col) not in self.board and (prev_row, prev_col) not in placement_map:
                break
            start_row, start_col = prev_row, prev_col

        coords: List[Coordinate] = []
        cur_row, cur_col = start_row, start_col
        while 0 <= cur_row < BOARD_SIZE and 0 <= cur_col < BOARD_SIZE:
            if (cur_row, cur_col) not in self.board and (cur_row, cur_col) not in placement_map:
                break
            coords.append((cur_row, cur_col))
            cur_row += dr
            cur_col += dc
        return coords

    def _build_word(self, coords: Sequence[Coordinate], placement_map: Dict[Coordinate, Placement]) -> str:
        letters: List[str] = []
        for coord in coords:
            if coord in placement_map:
                letters.append(placement_map[coord].letter)
            else:
                letters.append(self.board[coord].letter)
        return "".join(letters)

    def _validate_word(self, word: str) -> None:
        if word.upper() not in self.dictionary:
            raise MoveError(f"{word} is not a valid word")

    def _score_word(self, coords: Sequence[Coordinate], placement_map: Dict[Coordinate, Placement]) -> int:
        word_multiplier = 1
        score = 0
        for coord in coords:
            if coord in placement_map:
                placement = placement_map[coord]
                tile_score = 0 if placement.is_blank else LETTER_SCORES[placement.letter]
                letter_multiplier = 1
                premium = PREMIUM_SQUARES.get(coord)
                if premium == "DL":
                    letter_multiplier = 2
                elif premium == "TL":
                    letter_multiplier = 3
                elif premium in {"DW", "TW"}:
                    word_multiplier *= 2 if premium == "DW" else 3
                score += tile_score * letter_multiplier
            else:
                board_tile = self.board[coord]
                score += board_tile.score
        return score * word_multiplier

    def _apply_placements(self, player_id: str, placement_map: Dict[Coordinate, Placement]) -> None:
        player = self.players[player_id]
        # Remove tiles from rack
        for placement in placement_map.values():
            for index, tile in enumerate(player.rack):
                tile_key = tile.letter if not tile.is_blank else "?"
                if placement.is_blank and tile.is_blank:
                    player.rack.pop(index)
                    break
                if not placement.is_blank and tile_key == placement.letter:
                    player.rack.pop(index)
                    break
            else:
                raise MoveError(f"Tile {placement.letter} not found in rack")

        for coord, placement in placement_map.items():
            self.board[coord] = BoardTile(
                letter=placement.letter,
                is_blank=placement.is_blank,
                placed_by=player_id,
                turn_played=self.turn_number,
            )

    def _check_game_end(self) -> None:
        if self.status != "active":
            return
        rack_empty = all(len(player.rack) == 0 for player in self.players.values())
        if rack_empty and len(self.tile_bag) == 0:
            self.status = "completed"
            self._finalize_scores("tiles exhausted")

    # ------------------------------------------------------------------
    # State serialization
    # ------------------------------------------------------------------
    def to_player_view(self, player_id: str) -> dict:
        player = self.players[player_id]
        opponent_id = next(pid for pid in self.player_order if pid != player_id)
        opponent = self.players[opponent_id]
        clock_snapshot = self._clock_snapshot()
        server_time = datetime.utcnow().isoformat() + "Z"

        board_cells = [
            {
                "row": row,
                "col": col,
                "letter": tile.letter,
                "isBlank": tile.is_blank,
                "placedBy": tile.placed_by,
            }
            for (row, col), tile in self.board.items()
        ]

        return {
            "gameId": self.id,
            "status": self.status,
            "turn": self.current_player_id,
            "turnNumber": self.turn_number,
            "scores": {
                player_id: player.score,
                opponent_id: opponent.score,
            },
            "rack": [
                {
                    "letter": tile.letter if not tile.is_blank else "?",
                    "isBlank": tile.is_blank,
                }
                for tile in player.rack
            ],
            "board": board_cells,
            "bagCount": len(self.tile_bag),
            "moveHistory": [
                {
                    "turn": move.turn_number,
                    "playerId": move.player_id,
                    "type": move.move_type,
                    "score": move.score,
                    "words": move.words,
                }
                for move in self.move_history
            ],
            "opponent": {
                "playerId": opponent_id,
                "displayName": opponent.display_name,
                "rackCount": len(opponent.rack),
            },
            "you": {
                "playerId": player.player_id,
                "displayName": player.display_name,
            },
            "clocks": {
                player_id: int(clock_snapshot.get(player_id, 0)),
                opponent_id: int(clock_snapshot.get(opponent_id, 0)),
            },
            "serverTime": server_time,
            "result": self.result,
        }

    def _finalize_scores(self, reason: str) -> None:
        if self.result is not None:
            return
        scores = {player_id: state.score for player_id, state in self.players.items()}
        max_score = max(scores.values())
        leaders = [player_id for player_id, score in scores.items() if score == max_score]
        if len(leaders) == 1:
            winner = leaders[0]
            loser = next(pid for pid in self.player_order if pid != winner)
            self.result = {
                "winner": winner,
                "loser": loser,
                "reason": reason,
            }
        else:
            self.result = {
                "winner": "",
                "loser": "",
                "reason": "draw",
            }
