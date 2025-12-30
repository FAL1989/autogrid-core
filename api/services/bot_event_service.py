"""Bot event logging helpers."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import BotEvent


def _clean_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {key: value for key, value in metadata.items() if value is not None}


async def record_bot_event(
    db: AsyncSession,
    bot_id: UUID,
    user_id: UUID | None,
    event_type: str,
    source: str,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> BotEvent:
    event = BotEvent(
        bot_id=bot_id,
        user_id=user_id,
        event_type=event_type,
        source=source,
        reason=reason,
        metadata_json=_clean_metadata(metadata),
    )
    db.add(event)
    await db.flush()
    return event
