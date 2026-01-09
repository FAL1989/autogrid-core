"""Notification interfaces for bot events."""

from __future__ import annotations

import importlib
import os
from decimal import Decimal
from typing import Protocol
from uuid import UUID


class Notifier(Protocol):
    """Notification interface for bot events."""

    async def notify_order_filled(
        self,
        user_id: UUID,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
    ) -> None: ...

    async def notify_error(self, user_id: UUID, error: str) -> None: ...


class NullNotifier:
    """No-op notifier used by the open-source core."""

    async def notify_order_filled(
        self,
        user_id: UUID,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        return None

    async def notify_error(self, user_id: UUID, error: str) -> None:
        return None


def get_notifier() -> Notifier:
    """Resolve notifier implementation from environment or fallback to no-op."""
    path = os.getenv("AUTOGRID_NOTIFIER")
    if not path:
        return NullNotifier()
    try:
        module_path, attr = path.rsplit(":", 1)
        module = importlib.import_module(module_path)
        notifier_cls = getattr(module, attr)
        return notifier_cls()
    except Exception:
        return NullNotifier()
