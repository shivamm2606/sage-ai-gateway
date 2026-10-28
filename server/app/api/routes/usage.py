from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser
from app.core.config import settings
from app.db.session import DbSession
from app.models import UsageRecord
from app.schemas.conversation import ModelUsage, UsageSummary
from app.services.usage import period_start, totals_since

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("", response_model=UsageSummary)
async def get_usage(user: CurrentUser, db: DbSession) -> UsageSummary:
    since = period_start()
    totals = await totals_since(db, user.id, since)

    rows = await db.execute(
        select(
            UsageRecord.model,
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.prompt_tokens + UsageRecord.completion_tokens), 0),
            func.coalesce(func.avg(UsageRecord.latency_ms), 0),
        )
        .where(UsageRecord.user_id == user.id, UsageRecord.created_at >= since)
        .group_by(UsageRecord.model)
        .order_by(func.count(UsageRecord.id).desc())
    )

    request_limit = settings.daily_request_quota or None
    token_limit = settings.daily_token_quota or None
    return UsageSummary(
        period_start=since,
        requests=totals.requests,
        prompt_tokens=totals.prompt_tokens,
        completion_tokens=totals.completion_tokens,
        total_tokens=totals.total_tokens,
        request_limit=request_limit,
        token_limit=token_limit,
        requests_remaining=max(0, request_limit - totals.requests) if request_limit else None,
        tokens_remaining=max(0, token_limit - totals.total_tokens) if token_limit else None,
        by_model=[
            ModelUsage(model=m, requests=n, total_tokens=t, avg_latency_ms=round(lat))
            for m, n, t, lat in rows.all()
        ],
    )
