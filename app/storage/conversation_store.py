"""
Conversation storage using SQLModel — SQLite locally or PostgreSQL in production (e.g. EasyPanel).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import os
from sqlmodel import Field, Session, SQLModel, create_engine, select


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str = Field(default="Untitled Conversation", index=True)
    created_at: datetime = Field(default_factory=_utc_now, index=True)
    updated_at: datetime = Field(default_factory=_utc_now, index=True)


class ConversationMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversation.id", index=True)
    role: str = Field(index=True)  # user | assistant
    content: str
    mode_used: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now, index=True)


class ReflectionThread(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    conversation_id: str = Field(foreign_key="conversation.id", index=True)
    title: str = Field(default="Reflection", index=True)
    latest_draft_json: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now, index=True)
    updated_at: datetime = Field(default_factory=_utc_now, index=True)


class ReflectionMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: str = Field(foreign_key="reflectionthread.id", index=True)
    role: str = Field(index=True)  # user | assistant
    content: str
    created_at: datetime = Field(default_factory=_utc_now, index=True)


class ConversationStore:
    def __init__(self, database_url: str = "sqlite:///./storage/conversations.db"):
        url = (database_url or "").strip() or "sqlite:///./storage/conversations.db"
        # Heroku / some panels expose postgres://; SQLAlchemy expects postgresql+psycopg2
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://") :]

        if url.startswith("sqlite"):
            if url.startswith("sqlite:///./"):
                db_path = url.replace("sqlite:///", "", 1)
                db_dir = os.path.dirname(db_path)
                if db_dir:
                    os.makedirs(db_dir, exist_ok=True)
            self.engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
                max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            )

    def init(self) -> None:
        SQLModel.metadata.create_all(self.engine)

    def create_conversation(self, first_prompt: Optional[str] = None) -> Conversation:
        title = "Untitled Conversation"
        if first_prompt:
            compact = " ".join(first_prompt.strip().split())
            title = (compact[:72] + "...") if len(compact) > 75 else compact
        convo = Conversation(title=title, created_at=_utc_now(), updated_at=_utc_now())
        with Session(self.engine) as session:
            session.add(convo)
            session.commit()
            session.refresh(convo)
            return convo

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        with Session(self.engine) as session:
            return session.get(Conversation, conversation_id)

    def list_conversations(self, limit: int = 50) -> List[Conversation]:
        with Session(self.engine) as session:
            stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
            return list(session.exec(stmt).all())

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        mode_used: Optional[str] = None,
    ) -> ConversationMessage:
        with Session(self.engine) as session:
            msg = ConversationMessage(
                conversation_id=conversation_id,
                role=role,
                content=content,
                mode_used=mode_used,
                created_at=_utc_now(),
            )
            session.add(msg)

            convo = session.get(Conversation, conversation_id)
            if convo:
                convo.updated_at = _utc_now()
                session.add(convo)

            session.commit()
            session.refresh(msg)
            return msg

    def get_messages(self, conversation_id: str) -> List[ConversationMessage]:
        with Session(self.engine) as session:
            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.created_at.asc())
            )
            return list(session.exec(stmt).all())

    def create_reflection_thread(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        latest_draft_json: Optional[str] = None,
    ) -> ReflectionThread:
        thread = ReflectionThread(
            conversation_id=conversation_id,
            title=(title or "Reflection").strip()[:120] or "Reflection",
            latest_draft_json=latest_draft_json,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        with Session(self.engine) as session:
            session.add(thread)
            session.commit()
            session.refresh(thread)
            return thread

    def get_reflection_thread(self, thread_id: str) -> Optional[ReflectionThread]:
        with Session(self.engine) as session:
            return session.get(ReflectionThread, thread_id)

    def list_reflection_threads(self, conversation_id: str, limit: int = 50) -> List[ReflectionThread]:
        with Session(self.engine) as session:
            stmt = (
                select(ReflectionThread)
                .where(ReflectionThread.conversation_id == conversation_id)
                .order_by(ReflectionThread.updated_at.desc())
                .limit(limit)
            )
            return list(session.exec(stmt).all())

    def update_reflection_thread_draft(self, thread_id: str, latest_draft_json: str) -> Optional[ReflectionThread]:
        with Session(self.engine) as session:
            thread = session.get(ReflectionThread, thread_id)
            if not thread:
                return None
            thread.latest_draft_json = latest_draft_json
            thread.updated_at = _utc_now()
            session.add(thread)
            session.commit()
            session.refresh(thread)
            return thread

    def add_reflection_message(self, thread_id: str, role: str, content: str) -> ReflectionMessage:
        with Session(self.engine) as session:
            msg = ReflectionMessage(
                thread_id=thread_id,
                role=role,
                content=content,
                created_at=_utc_now(),
            )
            session.add(msg)
            thread = session.get(ReflectionThread, thread_id)
            if thread:
                thread.updated_at = _utc_now()
                session.add(thread)
            session.commit()
            session.refresh(msg)
            return msg

    def get_reflection_messages(self, thread_id: str) -> List[ReflectionMessage]:
        with Session(self.engine) as session:
            stmt = (
                select(ReflectionMessage)
                .where(ReflectionMessage.thread_id == thread_id)
                .order_by(ReflectionMessage.created_at.asc())
            )
            return list(session.exec(stmt).all())

