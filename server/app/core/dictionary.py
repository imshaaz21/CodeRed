from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Set

DEFAULT_DICTIONARY_PATH = Path(__file__).resolve().parents[3] / "CSW24.txt"


def _extract_word(raw_line: str) -> str | None:
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    first_token = stripped.split()[0]
    if not first_token:
        return None
    return first_token.upper()


def _load_words(path: Path) -> Set[str]:
    words: Set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            word = _extract_word(raw_line)
            if word:
                words.add(word)
    return words


@lru_cache(maxsize=1)
def get_dictionary(path: str | os.PathLike[str] | None = None) -> Set[str]:
    dictionary_path = Path(path) if path else DEFAULT_DICTIONARY_PATH
    if not dictionary_path.exists():
        raise FileNotFoundError(f"Dictionary file not found at {dictionary_path}")
    return _load_words(dictionary_path)
