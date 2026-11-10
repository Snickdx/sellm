"""Idempotent renames: legacy se_* course tables → unprefixed shared schema."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# Order matters for FK-safe renames (children after parents is fine with RENAME).
_TABLE_RENAMES: tuple[tuple[str, str], ...] = (
    ("se_scenarios", "scenarios"),
    ("se_scenario_personas", "scenario_personas"),
    ("se_scenario_facts", "scenario_facts"),
    ("se_teams", "teams"),
    ("se_team_members", "team_members"),
    ("se_audit_events", "audit_events"),
    ("se_repository_submissions", "repository_submissions"),
    ("se_exit_interview_sessions", "exit_interview_sessions"),
    ("se_interview_participants", "interview_participants"),
    ("se_interview_questions", "interview_questions"),
    ("se_interview_answers", "interview_answers"),
    ("se_assessments", "assessments"),
    ("se_voice_rooms", "voice_rooms"),
    ("se_voice_utterances", "voice_utterances"),
)

_DROP_TABLES: tuple[str, ...] = (
    "se_messages",
    "se_requirements_sessions",
)

_INDEX_RENAMES: tuple[tuple[str, str], ...] = (
    ("uq_se_scenario_slug_version", "uq_scenario_slug_version"),
    ("uq_se_scenario_persona", "uq_scenario_persona"),
    ("uq_se_scenario_fact", "uq_scenario_fact"),
    ("uq_se_team_member", "uq_team_member"),
    ("uq_se_team_commit", "uq_team_commit"),
    ("uq_se_interview_participant", "uq_interview_participant"),
    ("uq_se_assessment_session_user", "uq_assessment_session_user"),
    ("uq_se_voice_room_session", "uq_voice_room_session"),
)


def _table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def migrate_se_prefix(engine: Engine) -> list[str]:
    """Rename/drop legacy se_* tables. Returns human-readable actions taken."""
    actions: list[str] = []
    dialect = engine.dialect.name
    tables = _table_names(engine)

    with engine.begin() as conn:
        for old, new in _TABLE_RENAMES:
            if old in tables and new not in tables:
                conn.execute(text(f"ALTER TABLE {_quote_ident(old)} RENAME TO {_quote_ident(new)}"))
                actions.append(f"rename {old} -> {new}")
                tables.discard(old)
                tables.add(new)
            elif old in tables and new in tables:
                actions.append(f"skip rename {old} (both {old} and {new} exist)")

        for name in _DROP_TABLES:
            if name in tables:
                conn.execute(text(f"DROP TABLE {_quote_ident(name)}"))
                actions.append(f"drop {name}")
                tables.discard(name)

        if dialect == "postgresql":
            for old_idx, new_idx in _INDEX_RENAMES:
                try:
                    conn.execute(
                        text(
                            f"ALTER INDEX IF EXISTS {_quote_ident(old_idx)} "
                            f"RENAME TO {_quote_ident(new_idx)}"
                        )
                    )
                    actions.append(f"rename index {old_idx} -> {new_idx}")
                except Exception:
                    pass

    return actions


def ensure_course_columns(engine: Engine) -> None:
    """Best-effort additive columns for existing installs (new unprefixed names)."""
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE interview_participants ADD COLUMN display_name VARCHAR DEFAULT ''"
            )
    except Exception:
        pass
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE teams ADD COLUMN participant_names JSON")
    except Exception:
        pass
