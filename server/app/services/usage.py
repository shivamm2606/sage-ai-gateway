import math
from dataclasses import dataclass
from datetime import UTC, datetime, time

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import UsageRecord


def estimate_tokens(text: str) -> int:
    # rough rule of thumb (~4 chars per token) for providers that don't report usage
    return math.ceil(len(text) / 4) if text else 0


def period_start(now: datetime | None = None) -> datetime:
    # quotas reset every day at midnight utc
    now = now or datetime.now(UTC)
    return datetime.combine(now.date(), time.min, tzinfo=UTC)


@dataclass(frozen=True)
class Totals:
    requests: int
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


async def totals_since(db: AsyncSession, user_id: int, since: datetime) -> Totals:
    row = (
        await db.execute(
            select(
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
                func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
            ).where(UsageRecord.user_id == user_id, UsageRecord.created_at >= since)
        )
    ).one()
    return Totals(requests=row[0], prompt_tokens=row[1], completion_tokens=row[2])


async def enforce_quota(db: AsyncSession, user_id: int) -> None:
    totals = await totals_since(db, user_id, period_start())
    limit = None
    if settings.daily_request_quota and totals.requests >= settings.daily_request_quota:
        limit = f"daily request limit reached ({settings.daily_request_quota})"
    elif settings.daily_token_quota and totals.total_tokens >= settings.daily_token_quota:
        limit = f"daily token limit reached ({settings.daily_token_quota})"
    if limit:
        raise HTTPException(status_code=429, detail=f"{limit}, resets at 00:00 UTC")
