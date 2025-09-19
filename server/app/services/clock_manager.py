from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Dict

from .game_manager import GameManager
from .game_service import GameService


class ClockManager:
    def __init__(self, game_manager: GameManager, game_service: GameService, *, interval: float = 1.0) -> None:
        self.game_manager = game_manager
        self.game_service = game_service
        self._interval = interval
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def start(self, game_id: str) -> None:
        async with self._lock:
            if game_id in self._tasks:
                return
            task = asyncio.create_task(self._run_clock(game_id))
            self._tasks[game_id] = task

    async def stop(self, game_id: str) -> None:
        async with self._lock:
            task = self._tasks.pop(game_id, None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _run_clock(self, game_id: str) -> None:
        try:
            while True:
                game = await self.game_manager.get_game(game_id)
                if game is None:
                    return

                lock = await self.game_manager.get_lock(game_id)
                should_push = False
                async with lock:
                    clock_changed = game.sync_clock()
                    status = game.status
                    should_push = clock_changed or status != "active"

                if should_push:
                    await self.game_service.push_state(game, highlight="clock")

                if status != "active":
                    return

                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            return
        finally:
            async with self._lock:
                existing = self._tasks.get(game_id)
                if existing is asyncio.current_task():
                    self._tasks.pop(game_id, None)
