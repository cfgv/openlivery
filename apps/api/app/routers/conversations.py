import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import Agent, Conversation, Message, User, now_utc
from ..schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationInboxOut,
    ConversationModeUpdate,
    ConversationOut,
    SendMessageRequest,
)
from ..services.ai import chat_completion
from ..services.knowledge import build_system_prompt, retrieve_knowledge
from ..services.media import describe_image, transcribe_audio
from ..services.providers import resolve_agent_credentials, resolve_provider_credentials
from ..services.usage import record_usage
from ..services.whatsapp import send_whatsapp_message


router = APIRouter(prefix="/conversations", tags=["Conversations"])

MAX_MEDIA_BYTES = 20 * 1024 * 1024


def _conversation(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .options(
            selectinload(Conversation.messages),
            joinedload(Conversation.agent).joinedload(Agent.client),
        )
        .execution_options(populate_existing=True)
        .where(Conversation.id == conversation_id, Conversation.agency_id == user.agency_id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    agent_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Conversation).where(Conversation.agency_id == user.agency_id)
    if agent_id:
        query = query.where(Conversation.agent_id == agent_id)
    if client_id:
        query = query.where(Conversation.client_id == client_id)
    return db.scalars(query.order_by(Conversation.updated_at.desc())).all()


@router.get("/inbox", response_model=list[ConversationInboxOut])
def inbox(
    agent_id: uuid.UUID | None = None,
    channel: str | None = None,
    mode: str | None = None,
    search: str | None = None,
    unread: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Latest message per conversation, resolved in SQL so we never load full
    # message histories just to build the list.
    ranked = select(
        Message.conversation_id.label("cid"),
        Message.content.label("content"),
        Message.sender_type.label("sender_type"),
        Message.created_at.label("created_at"),
        func.row_number().over(partition_by=Message.conversation_id, order_by=Message.created_at.desc()).label("rn"),
    ).subquery()
    last = select(ranked).where(ranked.c.rn == 1).subquery()
    unread_counts = (
        select(Message.conversation_id.label("cid"), func.count(Message.id).label("n"))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.sender_type == "visitor",
            or_(Conversation.operator_read_at.is_(None), Message.created_at > Conversation.operator_read_at),
        )
        .group_by(Message.conversation_id)
    ).subquery()
    unread_count = func.coalesce(unread_counts.c.n, 0)

    query = (
        select(Conversation, Agent.name, last.c.content, unread_count.label("unread_count"))
        .join(Agent, Agent.id == Conversation.agent_id)
        .outerjoin(last, last.c.cid == Conversation.id)
        .outerjoin(unread_counts, unread_counts.c.cid == Conversation.id)
        .where(Conversation.agency_id == user.agency_id)
    )
    if agent_id:
        query = query.where(Conversation.agent_id == agent_id)
    if channel:
        query = query.where(Conversation.channel == channel)
    if mode in ("ai", "human"):
        query = query.where(Conversation.mode == mode)
    if unread:
        query = query.where(unread_count > 0)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Conversation.title).like(term),
                func.lower(func.coalesce(Conversation.contact_name, "")).like(term),
                func.lower(func.coalesce(last.c.content, "")).like(term),
            )
        )
    rows = db.execute(query.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)).all()
    return [
        {
            "id": conv.id,
            "agent_id": conv.agent_id,
            "agent_name": agent_name or "",
            "client_id": conv.client_id,
            "title": conv.title,
            "contact_name": conv.contact_name,
            "channel": conv.channel,
            "mode": conv.mode,
            "preview": (content or "")[:140].strip(),
            "unread": int(row_unread_count) > 0,
            "unread_count": int(row_unread_count),
            "updated_at": conv.updated_at,
        }
        for conv, agent_name, content, row_unread_count in rows
    ]


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    agent = db.scalar(select(Agent).where(Agent.id == payload.agent_id, Agent.agency_id == user.agency_id))
    if not agent:
        raise HTTPException(status_code=400, detail="The selected agent does not exist")
    conversation = Conversation(
        agency_id=user.agency_id,
        client_id=agent.client_id,
        agent_id=agent.id,
    )
    db.add(conversation)
    db.commit()
    return _conversation(db, user, conversation.id)


@router.post("/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(conversation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = _conversation(db, user, conversation_id)
    conversation.operator_read_at = now_utc()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _conversation(db, user, conversation_id)


def _ready_agent(db: Session, conversation: Conversation) -> tuple[Agent, tuple[str, str]]:
    """Validate the conversation can produce an AI reply and return the agent + credentials."""
    agent = conversation.agent
    if not agent.is_active:
        raise HTTPException(status_code=400, detail="This agent is inactive")
    credentials = resolve_agent_credentials(db, agent)
    if not credentials or not agent.model.strip():
        raise HTTPException(
            status_code=400,
            detail="This agent is not ready: set its model and add the provider API key in Settings.",
        )
    if conversation.mode == "human":
        raise HTTPException(status_code=409, detail="This conversation is being handled by a person")
    return agent, credentials


async def _generate_reply(
    db: Session,
    user: User,
    conversation: Conversation,
    agent: Agent,
    credentials: tuple[str, str],
    query: str,
) -> Conversation:
    """Run the agent over the current conversation and store the assistant reply."""
    knowledge = await retrieve_knowledge(db, agent, query)
    refreshed = _conversation(db, user, conversation.id)
    recent = refreshed.messages[-agent.memory_limit:] if agent.memory_limit else []
    history = [{"role": item.role, "content": item.content} for item in recent]
    messages = [{"role": "system", "content": build_system_prompt(agent, knowledge.text)}, *history]
    base_url, api_key = credentials
    completion = await chat_completion(
        agent.provider, base_url, api_key, agent.model.strip(), messages, temperature=agent.temperature, max_tokens=agent.max_tokens
    )
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=completion.text,
            sources=knowledge.sources,
            sender_type="ai",
            sender_name=agent.name,
        )
    )
    record_usage(db, agent.agency_id, agent.id, agent.provider, agent.model.strip(), completion)
    conversation.updated_at = now_utc()
    db.commit()
    return _conversation(db, user, conversation.id)


@router.post("/{conversation_id}/messages", response_model=ConversationDetail)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    agent, credentials = _ready_agent(db, conversation)

    content = payload.content.strip()
    if not conversation.messages:
        conversation.title = content[:80]
    conversation.updated_at = now_utc()
    db.add(Message(conversation_id=conversation.id, role="user", content=content, sender_type="visitor", sender_name="You"))
    db.commit()
    return await _generate_reply(db, user, conversation, agent, credentials, content)


@router.post("/{conversation_id}/media", response_model=ConversationDetail)
async def send_media_message(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    agent, credentials = _ready_agent(db, conversation)

    content_type = (file.content_type or "").lower()
    is_image = content_type.startswith("image/")
    is_audio = content_type.startswith("audio/") or content_type.startswith("video/ogg")
    if not is_image and not is_audio:
        raise HTTPException(status_code=400, detail="Only image or audio files are supported")
    if is_image and not agent.image_enabled:
        raise HTTPException(status_code=400, detail="Image recognition is disabled for this agent")
    if is_audio and not agent.audio_enabled:
        raise HTTPException(status_code=400, detail="Audio recognition is disabled for this agent")

    # Transcription and vision run on the agency's OpenAI key.
    media_credentials = resolve_provider_credentials(db, agent.agency_id, "openai")
    if not media_credentials:
        raise HTTPException(status_code=400, detail="Add an OpenAI API key in Settings to process media")

    data = await file.read(MAX_MEDIA_BYTES + 1)
    if len(data) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail="The file is too large (20 MB max)")
    base_url, api_key = media_credentials
    caption = caption.strip()

    if is_image:
        model = agent.image_model.strip() or agent.model.strip()
        instruction = (
            "Describe con detalle el contenido de esta imagen para que un asistente pueda responder al usuario."
            + (f" El usuario escribió: {caption}" if caption else "")
        )
        description = await describe_image(base_url, api_key, model, data, content_type, instruction)
        content = (f"{caption}\n\n" if caption else "") + f"[Imagen recibida] {description}"
    else:
        model = agent.audio_model.strip() or "whisper-1"
        transcript = await transcribe_audio(base_url, api_key, model, data, file.filename or "audio.ogg", content_type)
        content = (f"{caption}\n\n" if caption else "") + (transcript or "[Audio sin contenido reconocible]")

    if not conversation.messages:
        conversation.title = (caption or content)[:80]
    conversation.updated_at = now_utc()
    db.add(Message(conversation_id=conversation.id, role="user", content=content, sender_type="visitor", sender_name="You"))
    db.commit()
    return await _generate_reply(db, user, conversation, agent, credentials, content)


@router.patch("/{conversation_id}/mode", response_model=ConversationDetail)
def set_conversation_mode(
    conversation_id: uuid.UUID,
    payload: ConversationModeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    conversation.mode = payload.mode
    conversation.updated_at = now_utc()
    db.commit()
    return _conversation(db, user, conversation_id)


@router.post("/{conversation_id}/reply", response_model=ConversationDetail)
async def reply_as_human(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _conversation(db, user, conversation_id)
    if conversation.mode != "human":
        raise HTTPException(status_code=409, detail="Take control of the conversation before replying")
    external_message_id = await send_whatsapp_message(conversation, payload.content.strip())
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=payload.content.strip(),
            sender_type="human",
            sender_name=user.name,
            external_message_id=external_message_id,
        )
    )
    conversation.updated_at = now_utc()
    db.commit()
    return _conversation(db, user, conversation_id)
