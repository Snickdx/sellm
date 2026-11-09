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
    # Locked at create time (excel | yaml slug); persona may still change per turn
    scenario_slug: Optional[str] = Field(default=None, index=True)
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


ROLE_ADMIN = "admin"
ROLE_TESTER = "tester"
ROLE_STUDENT = "student"
VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_TESTER, ROLE_STUDENT})


def normalize_role(role: Optional[str], *, is_admin: bool = False) -> str:
    cleaned = (role or "").strip().lower()
    if cleaned in VALID_ROLES:
        return cleaned
    return ROLE_ADMIN if is_admin else ROLE_STUDENT


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    # ~15k ≈ one focused requirements interview (≈12–20 stakeholder turns)
    token_limit: int = Field(default=15_000, index=True)
    tokens_used: int = Field(default=0, index=True)
    is_admin: bool = Field(default=False, index=True)
    # admin | tester | student — students cannot pick mode/model
    role: str = Field(default=ROLE_STUDENT, index=True)
    # Cohort / lab section label (e.g. "morning", "cohort-a")
    group_name: Optional[str] = Field(default=None, index=True)
    # Instructor notes visible only to admins
    admin_notes: Optional[str] = Field(default=None)
    # Per-user defaults (testers/admins); students use AppSettings student_* defaults
    default_response_mode: Optional[str] = Field(default=None)
    default_llm_choice: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utc_now, index=True)

class AuthSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(unique=True, index=True)
    user_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_utc_now, index=True)

class UserApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    provider: str = Field(default="openai")
    api_key: str = Field(default="")
    base_url: Optional[str] = None
    updated_at: datetime = Field(default_factory=_utc_now, index=True)


class AppApiKey(SQLModel, table=True):
    """Shared platform API keys available to all users (billed against platform quota)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(unique=True, index=True)
    api_key: str = Field(default="")
    base_url: Optional[str] = None
    updated_at: datetime = Field(default_factory=_utc_now, index=True)


class AppSettings(SQLModel, table=True):
    """Singleton row (id=1) for app-wide / role defaults."""

    id: Optional[int] = Field(default=None, primary_key=True)
    # Defaults for testers/admins when they have no per-user override
    default_response_mode: str = Field(default="vector")
    default_llm_choice: Optional[str] = Field(default=None)
    # Locked defaults for all student-role accounts
    student_default_response_mode: str = Field(default="vector")
    student_default_llm_choice: Optional[str] = Field(default=None)
    updated_at: datetime = Field(default_factory=_utc_now, index=True)


class UserApiKeyProvider(SQLModel, table=False):
    provider: str
    api_key: str = ""
    base_url: Optional[str] = None
    has_key: bool = False


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
        self._ensure_user_token_columns()
        self._ensure_user_admin_columns()
        self._ensure_conversation_scenario_column()
        self._ensure_app_settings_row()

    def _ensure_user_token_columns(self) -> None:
        """Add token_limit / tokens_used on existing DBs created before quotas existed."""
        from sqlalchemy import inspect, text

        try:
            insp = inspect(self.engine)
            if "user" not in insp.get_table_names():
                return
            cols = {c["name"] for c in insp.get_columns("user")}
            with self.engine.begin() as conn:
                if "token_limit" not in cols:
                    default_limit = int(os.getenv("USER_TOKEN_LIMIT", "15000"))
                    conn.execute(
                        text(f"ALTER TABLE user ADD COLUMN token_limit INTEGER DEFAULT {default_limit}")
                    )
                if "tokens_used" not in cols:
                    conn.execute(text("ALTER TABLE user ADD COLUMN tokens_used INTEGER DEFAULT 0"))
        except Exception as exc:  # noqa: BLE001 — boot should continue if inspect fails
            print(f"[warn] Could not ensure user token columns: {exc}")

    def _ensure_user_admin_columns(self) -> None:
        """Add admin/group/notes/default/role columns on existing DBs."""
        from sqlalchemy import inspect, text

        try:
            insp = inspect(self.engine)
            if "user" not in insp.get_table_names():
                return
            cols = {c["name"] for c in insp.get_columns("user")}
            alters = []
            if "is_admin" not in cols:
                alters.append("ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0")
            if "role" not in cols:
                alters.append(f"ALTER TABLE user ADD COLUMN role VARCHAR DEFAULT '{ROLE_STUDENT}'")
            if "group_name" not in cols:
                alters.append("ALTER TABLE user ADD COLUMN group_name VARCHAR")
            if "admin_notes" not in cols:
                alters.append("ALTER TABLE user ADD COLUMN admin_notes VARCHAR")
            if "default_response_mode" not in cols:
                alters.append("ALTER TABLE user ADD COLUMN default_response_mode VARCHAR")
            if "default_llm_choice" not in cols:
                alters.append("ALTER TABLE user ADD COLUMN default_llm_choice VARCHAR")
            if alters:
                with self.engine.begin() as conn:
                    for stmt in alters:
                        conn.execute(text(stmt))
            self._backfill_user_roles()
        except Exception as exc:  # noqa: BLE001 — boot should continue if inspect fails
            print(f"[warn] Could not ensure user admin columns: {exc}")

    def _backfill_user_roles(self) -> None:
        """Assign roles for seeded accounts and cohort usernames on existing DBs."""
        with Session(self.engine) as session:
            changed = False
            for user in session.exec(select(User)).all():
                desired = self.default_role_for_username(
                    user.username,
                    is_admin=bool(getattr(user, "is_admin", False)),
                    existing_role=getattr(user, "role", None),
                )
                current = normalize_role(getattr(user, "role", None), is_admin=bool(user.is_admin))
                # Only force known seeded/cohort accounts; leave custom roles alone if already valid
                uname = (user.username or "").strip().lower()
                force = (
                    uname in self.DEFAULT_ADMIN_USERNAMES
                    or uname in self.DEFAULT_TESTER_USERNAMES
                    or uname.startswith("trainee")
                    or not (getattr(user, "role", None) or "").strip()
                )
                if force and current != desired:
                    user.role = desired
                    user.is_admin = desired == ROLE_ADMIN
                    session.add(user)
                    changed = True
                elif bool(user.is_admin) != (current == ROLE_ADMIN):
                    user.is_admin = current == ROLE_ADMIN
                    user.role = current
                    session.add(user)
                    changed = True
            if changed:
                session.commit()

    def _ensure_app_settings_row(self) -> None:
        from sqlalchemy import inspect, text

        try:
            insp = inspect(self.engine)
            if "appsettings" in insp.get_table_names():
                cols = {c["name"] for c in insp.get_columns("appsettings")}
                with self.engine.begin() as conn:
                    if "student_default_response_mode" not in cols:
                        conn.execute(
                            text(
                                "ALTER TABLE appsettings ADD COLUMN student_default_response_mode VARCHAR DEFAULT 'vector'"
                            )
                        )
                    if "student_default_llm_choice" not in cols:
                        conn.execute(
                            text("ALTER TABLE appsettings ADD COLUMN student_default_llm_choice VARCHAR")
                        )
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Could not ensure appsettings student columns: {exc}")

        with Session(self.engine) as session:
            row = session.get(AppSettings, 1)
            if row is None:
                session.add(
                    AppSettings(
                        id=1,
                        default_response_mode="vector",
                        default_llm_choice=None,
                        student_default_response_mode="vector",
                        student_default_llm_choice=None,
                    )
                )
                session.commit()
            else:
                if not getattr(row, "student_default_response_mode", None):
                    row.student_default_response_mode = row.default_response_mode or "vector"
                    session.add(row)
                    session.commit()

    def _ensure_conversation_scenario_column(self) -> None:
        """Add scenario_slug on existing DBs created before scenario-locked chats."""
        from sqlalchemy import inspect, text

        try:
            insp = inspect(self.engine)
            if "conversation" not in insp.get_table_names():
                return
            cols = {c["name"] for c in insp.get_columns("conversation")}
            if "scenario_slug" in cols:
                return
            with self.engine.begin() as conn:
                conn.execute(text("ALTER TABLE conversation ADD COLUMN scenario_slug VARCHAR"))
        except Exception as exc:  # noqa: BLE001 — boot should continue if inspect fails
            print(f"[warn] Could not ensure conversation.scenario_slug: {exc}")

    def create_conversation(
        self,
        first_prompt: Optional[str] = None,
        user_id: int = 0,
        scenario_slug: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Conversation:
        resolved_title = (title or "").strip() or "Untitled Conversation"
        if first_prompt and not (title or "").strip():
            compact = " ".join(first_prompt.strip().split())
            resolved_title = (compact[:72] + "...") if len(compact) > 75 else compact
        slug = (scenario_slug or "").strip() or None
        convo = Conversation(
            title=resolved_title,
            user_id=user_id,
            scenario_slug=slug,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
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
    DEFAULT_ADMIN_USERNAMES: frozenset[str] = frozenset({"nick"})
    DEFAULT_TESTER_USERNAMES: frozenset[str] = frozenset({"wayne", "claudine", "snick"})

    @classmethod
    def default_role_for_username(
        cls,
        username: str,
        *,
        is_admin: bool = False,
        existing_role: Optional[str] = None,
    ) -> str:
        uname = (username or "").strip().lower()
        if uname in cls.DEFAULT_ADMIN_USERNAMES or is_admin:
            return ROLE_ADMIN
        if uname in cls.DEFAULT_TESTER_USERNAMES:
            return ROLE_TESTER
        if uname.startswith("trainee"):
            return ROLE_STUDENT
        if existing_role and existing_role.strip().lower() in VALID_ROLES:
            return existing_role.strip().lower()
        return ROLE_STUDENT

    def create_user(
        self,
        username: str,
        password: str,
        *,
        token_limit: Optional[int] = None,
        reset_usage: bool = False,
        is_admin: Optional[bool] = None,
        role: Optional[str] = None,
        group_name: Optional[str] = None,
        admin_notes: Optional[str] = None,
        default_response_mode: Optional[str] = None,
        default_llm_choice: Optional[str] = None,
    ) -> User:
        """Create a user or update password if username already exists."""
        username = username.strip().lower()
        if not username:
            raise ValueError("Username is required")
        if not password:
            raise ValueError("Password is required")
        limit = int(token_limit if token_limit is not None else os.getenv("USER_TOKEN_LIMIT", "15000"))
        with Session(self.engine) as session:
            existing = session.exec(
                select(User).where(User.username == username)
            ).first()
            if existing:
                existing.password_hash = hash_password(password)
                existing.token_limit = limit
                if reset_usage:
                    existing.tokens_used = 0
                if role is not None:
                    resolved = normalize_role(role, is_admin=bool(is_admin))
                    existing.role = resolved
                    existing.is_admin = resolved == ROLE_ADMIN
                elif is_admin is not None:
                    existing.is_admin = bool(is_admin)
                    existing.role = ROLE_ADMIN if existing.is_admin else normalize_role(
                        getattr(existing, "role", None), is_admin=False
                    )
                    if existing.is_admin:
                        existing.role = ROLE_ADMIN
                    elif existing.role == ROLE_ADMIN:
                        existing.role = ROLE_STUDENT
                if group_name is not None:
                    existing.group_name = (group_name or "").strip() or None
                if admin_notes is not None:
                    existing.admin_notes = admin_notes
                if default_response_mode is not None:
                    existing.default_response_mode = (default_response_mode or "").strip() or None
                if default_llm_choice is not None:
                    existing.default_llm_choice = (default_llm_choice or "").strip() or None
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing
            if role is not None:
                resolved = normalize_role(role, is_admin=bool(is_admin))
            elif is_admin is True:
                resolved = ROLE_ADMIN
            else:
                resolved = self.default_role_for_username(username, is_admin=bool(is_admin))
            user = User(
                username=username,
                password_hash=hash_password(password),
                token_limit=limit,
                tokens_used=0,
                is_admin=resolved == ROLE_ADMIN,
                role=resolved,
                group_name=(group_name or "").strip() or None,
                admin_notes=admin_notes,
                default_response_mode=(default_response_mode or "").strip() or None,
                default_llm_choice=(default_llm_choice or "").strip() or None,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def list_users(self) -> List[User]:
        with Session(self.engine) as session:
            return list(session.exec(select(User).order_by(User.username)).all())

    def seed_users(self, extra: Optional[List[tuple[str, str]]] = None) -> List[str]:
        """Seed default users and sync nick/wayne/claudine/snick roles. Returns usernames created."""
        users = list(self.DEFAULT_USERS)
        if extra:
            users.extend(extra)
        created: List[str] = []
        with Session(self.engine) as session:
            for username, password in users:
                uname = username.strip().lower()
                role = self.default_role_for_username(uname)
                existing = session.exec(
                    select(User).where(User.username == uname)
                ).first()
                if not existing:
                    default_limit = int(os.getenv("USER_TOKEN_LIMIT", "15000"))
                    session.add(
                        User(
                            username=uname,
                            password_hash=hash_password(password),
                            token_limit=default_limit,
                            tokens_used=0,
                            is_admin=role == ROLE_ADMIN,
                            role=role,
                        )
                    )
                    created.append(uname)
                else:
                    existing.role = role
                    existing.is_admin = role == ROLE_ADMIN
                    session.add(existing)
            session.commit()
        self._backfill_user_roles()
        return created

    def update_user(
        self,
        user_id: int,
        *,
        token_limit: Optional[int] = None,
        tokens_used: Optional[int] = None,
        is_admin: Optional[bool] = None,
        role: Optional[str] = None,
        group_name: Optional[str] = None,
        clear_group: bool = False,
        admin_notes: Optional[str] = None,
        default_response_mode: Optional[str] = None,
        clear_default_response_mode: bool = False,
        default_llm_choice: Optional[str] = None,
        clear_default_llm_choice: bool = False,
        password: Optional[str] = None,
    ) -> Optional[User]:
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            if user is None:
                return None
            if token_limit is not None:
                user.token_limit = max(0, int(token_limit))
            if tokens_used is not None:
                user.tokens_used = max(0, int(tokens_used))
            if role is not None:
                resolved = normalize_role(role, is_admin=bool(is_admin))
                user.role = resolved
                user.is_admin = resolved == ROLE_ADMIN
            elif is_admin is not None:
                user.is_admin = bool(is_admin)
                user.role = ROLE_ADMIN if user.is_admin else (
                    ROLE_TESTER if normalize_role(getattr(user, "role", None)) == ROLE_TESTER else ROLE_STUDENT
                )
                if user.is_admin:
                    user.role = ROLE_ADMIN
                elif getattr(user, "role", None) == ROLE_ADMIN:
                    user.role = ROLE_STUDENT
            if clear_group:
                user.group_name = None
            elif group_name is not None:
                user.group_name = (group_name or "").strip() or None
            if admin_notes is not None:
                user.admin_notes = admin_notes
            if clear_default_response_mode:
                user.default_response_mode = None
            elif default_response_mode is not None:
                user.default_response_mode = (default_response_mode or "").strip() or None
            if clear_default_llm_choice:
                user.default_llm_choice = None
            elif default_llm_choice is not None:
                user.default_llm_choice = (default_llm_choice or "").strip() or None
            if password:
                user.password_hash = hash_password(password)
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
    def list_group_names(self) -> List[str]:
        with Session(self.engine) as session:
            rows = session.exec(
                select(User.group_name).where(User.group_name.is_not(None)).order_by(User.group_name)
            ).all()
            seen: set[str] = set()
            out: List[str] = []
            for name in rows:
                if not name or name in seen:
                    continue
                seen.add(name)
                out.append(name)
            return out

    def count_conversations_for_user(self, user_id: int) -> int:
        with Session(self.engine) as session:
            rows = session.exec(
                select(Conversation).where(Conversation.user_id == user_id)
            ).all()
            return len(list(rows))

    def list_conversations_for_user(self, user_id: int, limit: int = 200) -> List[Conversation]:
        with Session(self.engine) as session:
            stmt = (
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
            return list(session.exec(stmt).all())

    def token_usage_summary(self) -> Dict[str, Any]:
        users = self.list_users()
        total_limit = sum(int(u.token_limit or 0) for u in users)
        total_used = sum(int(u.tokens_used or 0) for u in users)
        exhausted = sum(1 for u in users if int(u.token_limit or 0) > 0 and int(u.tokens_used or 0) >= int(u.token_limit or 0))
        by_group: Dict[str, Dict[str, int]] = {}
        for u in users:
            key = (u.group_name or "").strip() or "(ungrouped)"
            bucket = by_group.setdefault(key, {"users": 0, "tokens_used": 0, "token_limit": 0})
            bucket["users"] += 1
            bucket["tokens_used"] += int(u.tokens_used or 0)
            bucket["token_limit"] += int(u.token_limit or 0)
        return {
            "user_count": len(users),
            "total_token_limit": total_limit,
            "total_tokens_used": total_used,
            "exhausted_users": exhausted,
            "by_group": by_group,
        }

    def get_app_settings(self) -> AppSettings:
        with Session(self.engine) as session:
            row = session.get(AppSettings, 1)
            if row is None:
                row = AppSettings(id=1, default_response_mode="vector")
                session.add(row)
                session.commit()
                session.refresh(row)
            return row

    def update_app_settings(
        self,
        *,
        default_response_mode: Optional[str] = None,
        default_llm_choice: Optional[str] = None,
        clear_default_llm_choice: bool = False,
        student_default_response_mode: Optional[str] = None,
        student_default_llm_choice: Optional[str] = None,
        clear_student_default_llm_choice: bool = False,
    ) -> AppSettings:
        with Session(self.engine) as session:
            row = session.get(AppSettings, 1)
            if row is None:
                row = AppSettings(id=1, default_response_mode="vector")
                session.add(row)
            if default_response_mode is not None:
                mode = (default_response_mode or "").strip() or "vector"
                row.default_response_mode = mode
            if clear_default_llm_choice:
                row.default_llm_choice = None
            elif default_llm_choice is not None:
                row.default_llm_choice = (default_llm_choice or "").strip() or None
            if student_default_response_mode is not None:
                row.student_default_response_mode = (
                    (student_default_response_mode or "").strip() or "vector"
                )
            if clear_student_default_llm_choice:
                row.student_default_llm_choice = None
            elif student_default_llm_choice is not None:
                row.student_default_llm_choice = (student_default_llm_choice or "").strip() or None
            row.updated_at = _utc_now()
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_all_app_api_configs(self) -> List[AppApiKey]:
        with Session(self.engine) as session:
            return list(session.exec(select(AppApiKey).order_by(AppApiKey.provider)).all())

    def get_app_api_config(self, provider: str) -> Optional[AppApiKey]:
        provider = (provider or "").strip().lower()
        with Session(self.engine) as session:
            return session.exec(
                select(AppApiKey).where(AppApiKey.provider == provider)
            ).first()

    def set_app_api_config(
        self,
        provider: str,
        api_key: str,
        base_url: Optional[str] = None,
    ) -> AppApiKey:
        provider = (provider or "").strip().lower()
        with Session(self.engine) as session:
            existing = session.exec(
                select(AppApiKey).where(AppApiKey.provider == provider)
            ).first()
            if existing:
                existing.api_key = api_key
                existing.base_url = base_url
                existing.updated_at = _utc_now()
            else:
                existing = AppApiKey(
                    provider=provider,
                    api_key=api_key,
                    base_url=base_url,
                )
                session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

    def check_token_quota(self, user_id: int, upcoming_tokens: int = 0) -> User:
        """Raise ValueError if the user has exhausted their token limit."""
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            if user is None:
                raise ValueError("User not found")
            used = int(user.tokens_used or 0)
            limit = int(user.token_limit or 0)
            if limit > 0 and used + upcoming_tokens > limit:
                raise ValueError(
                    f"Token limit reached ({used}/{limit}). Contact an instructor to raise your quota."
                )
            return user

    def add_tokens_used(self, user_id: int, tokens: int) -> User:
        """Increment tokens_used (clamped at zero). Returns updated user."""
        tokens = max(0, int(tokens or 0))
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            if user is None:
                raise ValueError("User not found")
            user.tokens_used = int(user.tokens_used or 0) + tokens
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def get_user_by_credentials(self, username: str, password: str) -> Optional[User]:
        username = (username or "").strip().lower()
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

    def get_user_api_config(self, user_id: int, provider: str) -> Optional[UserApiKey]:
        with Session(self.engine) as session:
            return session.exec(
                select(UserApiKey).where(
                    UserApiKey.user_id == user_id,
                    UserApiKey.provider == provider,
                )
            ).first()

    def get_all_user_api_configs(self, user_id: int) -> List[UserApiKey]:
        with Session(self.engine) as session:
            return list(
                session.exec(
                    select(UserApiKey).where(UserApiKey.user_id == user_id)
                ).all()
            )

    def set_user_api_config(self, user_id: int, provider: str, api_key: str, base_url: Optional[str] = None) -> UserApiKey:
        with Session(self.engine) as session:
            existing = session.exec(
                select(UserApiKey).where(
                    UserApiKey.user_id == user_id,
                    UserApiKey.provider == provider,
                )
            ).first()
            if existing:
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

