import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update

from app.api.deps import CurrentUser
from app.api.routes.conversations import get_owned_conversation
from app.core.config import settings
from app.db.session import DbSession, SessionMaker
from app.llm.base import ChatMessage, ProviderError, Usage
from app.llm.gateway import AUTO_MODEL, Gateway, get_gateway
from app.llm.router import RouteDecision
from app.models import Conversation, Message, UsageRecord
from app.schemas.conversation import MessageCreate, MessageResponse, MessageUsage
from app.services.usage import enforce_quota, estimate_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["chat"])

DEFAULT_TITLE = "New chat"


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


CODE_FENCE = re.compile(r"```.*?(```|$)", re.DOTALL)
MARKDOWN_CHARS = re.compile(r"[`*_#>~]+")


def make_title(content: str, limit: int = 60) -> str:
    # drop code blocks and markdown symbols so the sidebar shows readable text
    text = MARKDOWN_CHARS.sub("", CODE_FENCE.sub(" ", content))
    title = " ".join(text.split()).rstrip(":") or "Code snippet"
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def elapsed_ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    body: MessageCreate,
    user: CurrentUser,
    db: DbSession,
    sessions: SessionMaker,
    gateway: Annotated[Gateway, Depends(get_gateway)],
) -> StreamingResponse:
    conversation = await get_owned_conversation(db, user, conversation_id)

    requested = body.model or gateway.default_model
    if requested is None:
        raise HTTPException(status_code=503, detail="no models are configured")
    if requested == AUTO_MODEL and gateway.router is None:
        raise HTTPException(status_code=400, detail="auto routing is not configured")
    if requested != AUTO_MODEL and not gateway.has_model(requested):
        raise HTTPException(status_code=400, detail=f"unknown model: {requested}")

    await enforce_quota(db, user.id)

    # only finished messages go back to the model, errored or cut-off replies are skipped
    rows = list(
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id, Message.status == "complete")
            .order_by(Message.id.desc())
            .limit(settings.max_history_messages)
        )
    )
    history = [ChatMessage("system", settings.system_prompt)]
    history += [ChatMessage(m.role, m.content) for m in reversed(rows)]  # type: ignore[arg-type]
    history.append(ChatMessage("user", body.content))

    decision: RouteDecision | None = None
    model = requested
    if requested == AUTO_MODEL:
        assert gateway.router is not None
        decision = gateway.router.route(body.content, history_messages=len(rows))
        model = decision.model
        logger.info("auto routed to %s (score %d): %s", model, decision.score, decision.reason)

    user_message = Message(conversation_id=conversation.id, role="user", content=body.content)
    db.add(user_message)
    if conversation.title == DEFAULT_TITLE:
        conversation.title = make_title(body.content)
    conversation.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user_message)
    user_payload = MessageResponse.model_validate(user_message).model_dump(mode="json")
    title = conversation.title
    user_id = user.id
    prompt_estimate = sum(estimate_tokens(m.content) for m in history)

    async def save_reply(
        content: str,
        used_model: str,
        status: str,
        usage: Usage | None,
        started_at: float,
        first_token_ms: int | None,
    ) -> dict[str, Any]:
        async with sessions() as session:
            reply = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                model=used_model,
                status=status,
            )
            session.add(reply)
            await session.flush()

            record = UsageRecord(
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=reply.id,
                requested_model=requested,
                model=used_model,
                status=status,
                prompt_tokens=usage.prompt_tokens if usage else prompt_estimate,
                completion_tokens=usage.completion_tokens if usage else estimate_tokens(content),
                tokens_estimated=usage is None,
                latency_ms=elapsed_ms(started_at),
                first_token_ms=first_token_ms,
                routing_tier=decision.tier if decision else None,
                routing_score=decision.score if decision else None,
                routing_reason=decision.reason if decision else None,
            )
            session.add(record)
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(updated_at=func.now())
            )
            await session.commit()
            await session.refresh(reply)

            payload = MessageResponse.model_validate(reply)
            payload.usage = MessageUsage.model_validate(record)
            return payload.model_dump(mode="json")

    async def events() -> AsyncIterator[str]:
        routing = (
            {"tier": decision.tier, "score": decision.score, "reason": decision.reason}
            if decision
            else None
        )
        yield sse(
            "start",
            {
                "user_message": user_payload,
                "model": model,
                "requested_model": requested,
                "routing": routing,
                "title": title,
            },
        )

        started_at = time.perf_counter()
        first_token_ms: int | None = None
        parts: list[str] = []
        used_model = model
        usage: Usage | None = None
        error: str | None = None
        try:
            async for chunk in gateway.stream(model, history):
                used_model = chunk.model
                if chunk.usage is not None:
                    usage = chunk.usage
                    continue
                if first_token_ms is None:
                    first_token_ms = elapsed_ms(started_at)
                parts.append(chunk.text)
                yield sse("delta", {"text": chunk.text, "model": chunk.model})
        except ProviderError as err:
            error = str(err)
        except asyncio.CancelledError, GeneratorExit:
            # client went away (stop button / closed tab), keep what we got so far
            task = asyncio.ensure_future(
                save_reply(
                    "".join(parts), used_model, "cancelled", usage, started_at, first_token_ms
                )
            )
            await asyncio.shield(task)
            raise
        except Exception:
            logger.exception("unexpected error while streaming conversation %s", conversation_id)
            error = "internal error while generating a reply"

        status = "complete" if error is None else "error"
        reply = await save_reply(
            "".join(parts), used_model, status, usage, started_at, first_token_ms
        )
        if error is None:
            yield sse("done", {"message": reply})
        else:
            yield sse("error", {"detail": error, "message": reply})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
