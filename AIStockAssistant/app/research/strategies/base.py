from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.data.models import Bar


class Strategy(ABC):
    """Research strategy: emits target weight in [0, 1] per bar (same length as bars)."""

    strategy_id: str = "base"
    name: str = "Base"
    description: str = ""

    def __init__(self, **params: Any) -> None:
        self.params = params

    @abstractmethod
    def generate(self, bars: list[Bar]) -> list[float]:
        raise NotImplementedError
