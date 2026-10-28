from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app.api.deps import CurrentUser
from app.db.session import DbSession
from app.models import Conversation, Message, UsageRecord, User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationResponse,
    ConversationUpdate,
    MessageResponse,
    MessageUsage,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def get_owned_conversation(db: DbSession, user: User, conversation_id: int) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    # 404 for other users' chats too, so ids can't be probed
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


@router.post("", status_code=201, response_model=ConversationResponse)
async def create_conversation(
    body: ConversationCreate, user: CurrentUser, db: DbSession
) -> Conversation:
    conversation = Conversation(user_id=user.id)
    if body.title:
        conversation.title = body.title.strip()
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Conversation]:
    rows = await db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int, user: CurrentUser, db: DbSession
) -> ConversationDetail:
    conversation = await get_owned_conversation(db, user, conversation_id)
    messages = list(
        await db.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id)
        )
    )
    records = await db.scalars(
        select(UsageRecord).where(UsageRecord.message_id.in_([m.id for m in messages]))
    )
    usage_by_message = {r.message_id: MessageUsage.model_validate(r) for r in records}

    out = []
    for m in messages:
        item = MessageResponse.model_validate(m)
        item.usage = usage_by_message.get(m.id)
        out.append(item)
    return ConversationDetail(
        **ConversationResponse.model_validate(conversation).model_dump(), messages=out
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: int, body: ConversationUpdate, user: CurrentUser, db: DbSession
) -> Conversation:
    conversation = await get_owned_conversation(db, user, conversation_id)
    conversation.title = body.title.strip()
    conversation.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: int, user: CurrentUser, db: DbSession) -> Response:
    conversation = await get_owned_conversation(db, user, conversation_id)
    # messages go with it through ON DELETE CASCADE
    await db.delete(conversation)
    await db.commit()
    return Response(status_code=204)
