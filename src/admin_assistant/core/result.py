from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


T = TypeVar("T")


class ErrorInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class OperationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    error: ErrorInfo | None = None


class PagedResult(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    items: tuple[T, ...]
    total_count: int

