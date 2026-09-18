"""Serializes all access to a ``PymolBackend`` onto a single worker thread.

PyMOL's C layer is not thread-safe, and a ``pymol2.PyMOL()`` instance must be
driven consistently from one thread. FastMCP tools are async and may be
invoked concurrently by the client, so every backend call is funnelled
through a one-worker ``ThreadPoolExecutor`` and an ``asyncio.Lock``. Do not
call a backend method directly from tool code -- always go through
``PymolSession``.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .backends.base import PymolBackend


class PymolSession:
    def __init__(self, backend: PymolBackend) -> None:
        self._backend = backend
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pymol")
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await self._run(self._backend.start)

    async def call(self, fn: str, *args: Any, **kwargs: Any) -> Any:
        return await self._run(self._backend.call, fn, *args, **kwargs)

    async def do(self, command: str) -> str:
        return await self._run(self._backend.do, command)

    async def eval_json(self, code: str, **variables: Any) -> Any:
        return await self._run(self._backend.eval_json, code, **variables)

    async def close(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, self._backend.close)
        self._executor.shutdown(wait=True)

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self._executor, lambda: fn(*args, **kwargs)
            )
