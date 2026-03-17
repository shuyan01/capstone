"""
analytics/feedback_store.py

SQLite-backed recruiter feedback storage and analytics helpers.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


FEEDBACK_DB_PATH = os.getenv("FEEDBACK_DB_PATH", "./data/processed/feedback.db")


def get_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with Row mapping enabled."""
    db_path = Path(FEEDBACK_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_feedback_store() -> None:
    """Creates the feedback table if it does not already exist."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recruiter_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resume_id TEXT NOT NULL,
                job_query TEXT NOT NULL,
                feedback_label TEXT NOT NULL,
                notes TEXT,
                rank_position INTEGER,
                composite_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS interview_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resume_id TEXT NOT NULL,
                job_query TEXT NOT NULL,
                interview_round TEXT NOT NULL,
                scheduled_for TEXT NOT NULL,
                interviewer_name TEXT NOT NULL,
                meeting_link TEXT,
                status TEXT NOT NULL DEFAULT 'scheduled',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS handoff_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resume_id TEXT NOT NULL,
                job_query TEXT NOT NULL,
                sender_role TEXT NOT NULL,
                recipient_role TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def save_feedback(
    *,
    resume_id: str,
    job_query: str,
    feedback_label: str,
    notes: str | None = None,
    rank_position: int | None = None,
    composite_score: float | None = None,
) -> dict:
    """Persists one recruiter feedback record and returns it."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO recruiter_feedback (
                resume_id, job_query, feedback_label, notes, rank_position, composite_score
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                resume_id,
                job_query,
                feedback_label,
                notes,
                rank_position,
                composite_score,
            ),
        )
        conn.commit()
        feedback_id = cursor.lastrowid

    return {
        "id": feedback_id,
        "resume_id": resume_id,
        "job_query": job_query,
        "feedback_label": feedback_label,
        "notes": notes or "",
        "rank_position": rank_position,
        "composite_score": composite_score,
    }


def get_recent_feedback(limit: int = 10) -> list[dict]:
    """Returns recent recruiter feedback entries."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, resume_id, job_query, feedback_label, notes, rank_position, composite_score, created_at
            FROM recruiter_feedback
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_feedback_analytics() -> dict:
    """Computes simple aggregate analytics from recruiter feedback."""
    with get_connection() as conn:
        total_feedback = conn.execute(
            "SELECT COUNT(*) AS count FROM recruiter_feedback"
        ).fetchone()["count"]

        positive_feedback = conn.execute(
            "SELECT COUNT(*) AS count FROM recruiter_feedback WHERE feedback_label = 'positive'"
        ).fetchone()["count"]

        negative_feedback = conn.execute(
            "SELECT COUNT(*) AS count FROM recruiter_feedback WHERE feedback_label = 'negative'"
        ).fetchone()["count"]

        avg_score_row = conn.execute(
            "SELECT AVG(composite_score) AS avg_score FROM recruiter_feedback"
        ).fetchone()
        avg_score = avg_score_row["avg_score"] if avg_score_row["avg_score"] is not None else 0.0

        top_resumes = conn.execute(
            """
            SELECT resume_id, COUNT(*) AS feedback_count
            FROM recruiter_feedback
            GROUP BY resume_id
            ORDER BY feedback_count DESC, resume_id ASC
            LIMIT 5
            """
        ).fetchall()

        common_queries = conn.execute(
            """
            SELECT job_query, COUNT(*) AS usage_count
            FROM recruiter_feedback
            GROUP BY job_query
            ORDER BY usage_count DESC, job_query ASC
            LIMIT 5
            """
        ).fetchall()

        feedback_trend = conn.execute(
            """
            SELECT DATE(created_at) AS bucket,
                   SUM(CASE WHEN feedback_label = 'positive' THEN 1 ELSE 0 END) AS positive_feedback,
                   SUM(CASE WHEN feedback_label = 'negative' THEN 1 ELSE 0 END) AS negative_feedback,
                   COUNT(*) AS total_feedback
            FROM recruiter_feedback
            GROUP BY DATE(created_at)
            ORDER BY bucket DESC
            LIMIT 7
            """
        ).fetchall()

        interviews_summary = conn.execute(
            """
            SELECT interview_round,
                   COUNT(*) AS total_count,
                   SUM(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) AS scheduled_count
            FROM interview_schedule
            GROUP BY interview_round
            ORDER BY total_count DESC, interview_round ASC
            LIMIT 6
            """
        ).fetchall()

        handoff_summary = conn.execute(
            """
            SELECT recipient_role,
                   COUNT(*) AS total_count
            FROM handoff_notes
            GROUP BY recipient_role
            ORDER BY total_count DESC, recipient_role ASC
            LIMIT 6
            """
        ).fetchall()

    positive_rate = (positive_feedback / total_feedback) if total_feedback else 0.0

    return {
        "total_feedback": total_feedback,
        "positive_feedback": positive_feedback,
        "negative_feedback": negative_feedback,
        "positive_rate": round(positive_rate, 3),
        "avg_composite_score": round(float(avg_score), 3),
        "top_resumes": [dict(row) for row in top_resumes],
        "common_queries": [dict(row) for row in common_queries],
        "feedback_trend": [dict(row) for row in reversed(feedback_trend)],
        "interviews_summary": [dict(row) for row in interviews_summary],
        "handoff_summary": [dict(row) for row in handoff_summary],
        "recent_feedback": get_recent_feedback(limit=8),
    }


def create_interview_schedule(
    *,
    resume_id: str,
    job_query: str,
    interview_round: str,
    scheduled_for: str,
    interviewer_name: str,
    meeting_link: str | None = None,
) -> dict:
    """Creates an interview schedule record."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO interview_schedule (
                resume_id, job_query, interview_round, scheduled_for, interviewer_name, meeting_link
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                resume_id,
                job_query,
                interview_round,
                scheduled_for,
                interviewer_name,
                meeting_link,
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid

    return {
        "id": row_id,
        "resume_id": resume_id,
        "job_query": job_query,
        "interview_round": interview_round,
        "scheduled_for": scheduled_for,
        "interviewer_name": interviewer_name,
        "meeting_link": meeting_link or "",
        "status": "scheduled",
    }


def list_interview_schedule(resume_id: str | None = None, limit: int = 20) -> list[dict]:
    """Lists scheduled interviews, optionally filtered by resume_id."""
    with get_connection() as conn:
        if resume_id:
            rows = conn.execute(
                """
                SELECT id, resume_id, job_query, interview_round, scheduled_for, interviewer_name,
                       meeting_link, status, created_at
                FROM interview_schedule
                WHERE resume_id = ?
                ORDER BY scheduled_for DESC, id DESC
                LIMIT ?
                """,
                (resume_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, resume_id, job_query, interview_round, scheduled_for, interviewer_name,
                       meeting_link, status, created_at
                FROM interview_schedule
                ORDER BY scheduled_for DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def create_handoff_note(
    *,
    resume_id: str,
    job_query: str,
    sender_role: str,
    recipient_role: str,
    note: str,
) -> dict:
    """Creates a recruiter-to-hiring-manager handoff note."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO handoff_notes (
                resume_id, job_query, sender_role, recipient_role, note
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (resume_id, job_query, sender_role, recipient_role, note),
        )
        conn.commit()
        row_id = cursor.lastrowid

    return {
        "id": row_id,
        "resume_id": resume_id,
        "job_query": job_query,
        "sender_role": sender_role,
        "recipient_role": recipient_role,
        "note": note,
    }


def list_handoff_notes(resume_id: str | None = None, limit: int = 20) -> list[dict]:
    """Lists recruiter/hiring-manager handoff notes."""
    with get_connection() as conn:
        if resume_id:
            rows = conn.execute(
                """
                SELECT id, resume_id, job_query, sender_role, recipient_role, note, created_at
                FROM handoff_notes
                WHERE resume_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (resume_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, resume_id, job_query, sender_role, recipient_role, note, created_at
                FROM handoff_notes
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]
