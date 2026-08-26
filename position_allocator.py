"""Research-only position allocator for realistic replay accounting.

It prevents overlapping signals from implicitly using more than the configured
account allocation. No live execution is connected to this module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    opened_at: str
    closed_at: str | None
    allocation_pct: float
    direction: str


class AllocationBook:
    def __init__(self, max_total_pct: float = 5.0, allow_opposite: bool = False):
        self.max_total_pct = max_total_pct
        self.allow_opposite = allow_opposite
        self.positions: list[Position] = []

    def active(self, timestamp: str) -> list[Position]:
        return [p for p in self.positions if p.opened_at <= timestamp and (p.closed_at is None or timestamp < p.closed_at)]

    def can_open(self, timestamp: str, direction: str, allocation_pct: float) -> bool:
        if allocation_pct <= 0 or allocation_pct > self.max_total_pct:
            return False
        active = self.active(timestamp)
        if not self.allow_opposite and any(p.direction != direction for p in active):
            return False
        used = sum(p.allocation_pct for p in active)
        return used + allocation_pct <= self.max_total_pct

    def open(self, timestamp: str, direction: str, allocation_pct: float) -> bool:
        if not self.can_open(timestamp, direction, allocation_pct):
            return False
        self.positions.append(Position(timestamp, None, allocation_pct, direction))
        return True

    def close(self, index: int, timestamp: str) -> None:
        position = self.positions[index]
        if position.closed_at is None:
            self.positions[index] = Position(position.opened_at, timestamp, position.allocation_pct, position.direction)
