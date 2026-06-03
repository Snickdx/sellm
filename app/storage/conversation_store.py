"""
Conversation storage using SQLModel — SQLite locally or PostgreSQL in production (e.g. EasyPanel).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import hashlib
import os
from sqlmodel import Field, Session, SQLModel, create_engine, select


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str = Field(default="Untitled Conversation", index=True)
    user_id: int = Field(default=0, index=True)
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


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=_utc_now, index=True)

class AuthSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(unique=True, index=True)
    user_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_utc_now, index=True)

class UserApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(unique=True, index=True)
    provider: str = Field(default="openai")
    api_key: str = Field(default="")
    base_url: Optional[str] = None
    updated_at: datetime = Field(default_factory=_utc_now, index=True)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


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

    def create_conversation(self, first_prompt: Optional[str] = None, user_id: int = 0) -> Conversation:
        title = "Untitled Conversation"
        if first_prompt:
            compact = " ".join(first_prompt.strip().split())
            title = (compact[:72] + "...") if len(compact) > 75 else compact
        convo = Conversation(title=title, user_id=user_id, created_at=_utc_now(), updated_at=_utc_now())
        with Session(self.engine) as session:
            session.add(convo)
            session.commit()
            session.refresh(convo)
            return convo

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        with Session(self.engine) as session:
            return session.get(Conversation, conversation_id)

    def list_conversations(self, user_id: int = 0, limit: int = 50) -> List[Conversation]:
        with Session(self.engine) as session:
            stmt = (
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
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

    def delete_conversation(self, conversation_id: str) -> bool:
        with Session(self.engine) as session:
            convo = session.get(Conversation, conversation_id)
            if not convo:
                return False

            msg_stmt = select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation_id
            )
            for msg in session.exec(msg_stmt).all():
                session.delete(msg)

            thread_stmt = select(ReflectionThread).where(
                ReflectionThread.conversation_id == conversation_id
            )
            for thread in session.exec(thread_stmt).all():
                ref_msg_stmt = select(ReflectionMessage).where(
                    ReflectionMessage.thread_id == thread.id
                )
                for ref_msg in session.exec(ref_msg_stmt).all():
                    session.delete(ref_msg)
                session.delete(thread)

            session.delete(convo)
            session.commit()
            return True

    # ── User / Auth / API key methods ──────────────────────────

    DEFAULT_USERS: tuple[tuple[str, str], ...] = (
        ("nick", "badPassword1"),
        ("wayne", "badPassword1"),
        ("claudine", "badPassword1"),
        ("snick", "badPassword1"),
    )

    def create_user(self, username: str, password: str) -> User:
        """Create a user or update password if username already exists."""
        username = username.strip().lower()
        if not username:
            raise ValueError("Username is required")
        if not password:
            raise ValueError("Password is required")
        with Session(self.engine) as session:
            existing = session.exec(
                select(User).where(User.username == username)
            ).first()
            if existing:
                existing.password_hash = hash_password(password)
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing
            user = User(username=username, password_hash=hash_password(password))
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def list_users(self) -> List[User]:
        with Session(self.engine) as session:
            return list(session.exec(select(User).order_by(User.username)).all())

    def seed_users(self, extra: Optional[List[tuple[str, str]]] = None) -> List[str]:
        """Seed default training users if they don't exist. Returns usernames created."""
        users = list(self.DEFAULT_USERS)
        if extra:
            users.extend(extra)
        created: List[str] = []
        with Session(self.engine) as session:
            for username, password in users:
                uname = username.strip().lower()
                existing = session.exec(
                    select(User).where(User.username == uname)
                ).first()
                if not existing:
                    session.add(
                        User(
                            username=uname,
                            password_hash=hash_password(password),
                        )
                    )
                    created.append(uname)
            session.commit()
        return created

    def get_user_by_credentials(self, username: str, password: str) -> Optional[User]:
        with Session(self.engine) as session:
            user = session.exec(
                select(User).where(User.username == username)
            ).first()
            if user and user.password_hash == hash_password(password):
                return user
            return None

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with Session(self.engine) as session:
            return session.get(User, user_id)

    def create_session(self, user_id: int) -> str:
        token = str(uuid4())
        with Session(self.engine) as session:
            sess = AuthSession(token=token, user_id=user_id)
            session.add(sess)
            session.commit()
        return token

    def get_session(self, token: str) -> Optional[AuthSession]:
        with Session(self.engine) as session:
            return session.exec(
                select(AuthSession).where(AuthSession.token == token)
            ).first()

    def delete_session(self, token: str) -> None:
        with Session(self.engine) as session:
            sess = session.exec(
                select(AuthSession).where(AuthSession.token == token)
            ).first()
            if sess:
                session.delete(sess)
                session.commit()

    def get_user_api_config(self, user_id: int) -> Optional[UserApiKey]:
        with Session(self.engine) as session:
            return session.exec(
                select(UserApiKey).where(UserApiKey.user_id == user_id)
            ).first()

    def set_user_api_config(self, user_id: int, provider: str, api_key: str, base_url: Optional[str] = None) -> UserApiKey:
        with Session(self.engine) as session:
            existing = session.exec(
                select(UserApiKey).where(UserApiKey.user_id == user_id)
            ).first()
            if existing:
                existing.provider = provider
                existing.api_key = api_key
                existing.base_url = base_url
                existing.updated_at = _utc_now()
            else:
                existing = UserApiKey(
                    user_id=user_id,
                    provider=provider,
                    api_key=api_key,
                    base_url=base_url,
                )
                session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

