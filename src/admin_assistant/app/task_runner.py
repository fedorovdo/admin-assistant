from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any


class TaskRunner:
    def submit(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
        raise NotImplementedError


class DefaultTaskRunner(TaskRunner):
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
        return self._executor.submit(func, *args, **kwargs)

