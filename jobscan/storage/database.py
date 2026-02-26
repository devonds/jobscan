"""SQLite database operations for job storage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from jobscan.storage.models import CREATE_TABLES, SCHEMA_VERSION

if TYPE_CHECKING:
    from jobscan.models.slack import SlackJobPosting


class DatabaseError(Exception):
    """Database operation error."""

    pass


class Database:
    """SQLite database for storing scraped job postings."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._ensure_directory()
        self._ensure_schema()

    def _ensure_directory(self) -> None:
        """Create database directory if needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            raise DatabaseError(f"Database error: {e}") from e
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        with self._connection() as conn:
            conn.executescript(CREATE_TABLES)

            # Check and set schema version
            cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )

    def upsert_job(self, job: SlackJobPosting) -> int:
        """Insert or update a job posting. Returns row ID."""
        skills_json = json.dumps(job.skills) if job.skills else None

        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO slack_jobs (
                    message_ts, channel_id, channel_name, workspace,
                    posted_by_user_id, posted_at, company, position,
                    location, salary_min, salary_max, salary_currency,
                    employment_type, work_mode, raw_message, parsed_description,
                    job_url, scraped_description, skills_mentioned, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_ts, channel_id) DO UPDATE SET
                    company = excluded.company,
                    position = excluded.position,
                    location = excluded.location,
                    salary_min = excluded.salary_min,
                    salary_max = excluded.salary_max,
                    employment_type = excluded.employment_type,
                    work_mode = excluded.work_mode,
                    parsed_description = excluded.parsed_description,
                    job_url = excluded.job_url,
                    scraped_description = excluded.scraped_description,
                    skills_mentioned = excluded.skills_mentioned,
                    updated_at = excluded.updated_at
                RETURNING id
                """,
                (
                    job.message_ts,
                    job.channel_id,
                    job.channel_name,
                    job.workspace,
                    job.posted_by_user_id,
                    job.posted_at,
                    job.company,
                    job.position,
                    job.location,
                    job.salary_min,
                    job.salary_max,
                    job.salary_currency,
                    job.employment_type,
                    job.work_mode,
                    job.raw_message,
                    job.parsed_description,
                    job.job_url,
                    job.scraped_description,
                    skills_json,
                    datetime.now(),
                ),
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_job_by_id(self, job_id: int) -> SlackJobPosting | None:
        """Get a job by its database ID."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM slack_jobs WHERE id = ?",
                (job_id,),
            )
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def get_jobs(
        self,
        channel_id: str | None = None,
        workspace: str | None = None,
        company: str | None = None,
        work_mode: str | None = None,
        unapplied_only: bool = False,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SlackJobPosting]:
        """Query jobs with optional filters."""
        conditions = []
        params: list = []

        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)
        if workspace:
            conditions.append("workspace = ?")
            params.append(workspace)
        if company:
            conditions.append("company LIKE ?")
            params.append(f"%{company}%")
        if work_mode:
            conditions.append("work_mode = ?")
            params.append(work_mode)
        if unapplied_only:
            conditions.append("applied = FALSE")
        if since:
            conditions.append("posted_at >= ?")
            params.append(since)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.extend([limit, offset])

        with self._connection() as conn:
            cursor = conn.execute(
                f"""
                SELECT * FROM slack_jobs
                WHERE {where_clause}
                ORDER BY posted_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            return [self._row_to_job(row) for row in cursor.fetchall()]

    def get_all_jobs(self, since: datetime | None = None) -> list[SlackJobPosting]:
        """Get all jobs, optionally since a date."""
        return self.get_jobs(since=since, limit=10000)

    def count_jobs(
        self,
        channel_id: str | None = None,
        unapplied_only: bool = False,
    ) -> int:
        """Count jobs matching filters."""
        conditions = []
        params: list = []

        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)
        if unapplied_only:
            conditions.append("applied = FALSE")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._connection() as conn:
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM slack_jobs WHERE {where_clause}",
                params,
            )
            return cursor.fetchone()[0]

    def mark_job_applied(self, job_id: int) -> bool:
        """Mark a job as applied. Returns True if updated."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE slack_jobs
                SET applied = TRUE, applied_at = ?
                WHERE id = ? AND applied = FALSE
                """,
                (datetime.now(), job_id),
            )
            return cursor.rowcount > 0

    def update_match_score(self, job_id: int, score: float) -> None:
        """Update the match score for a job."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE slack_jobs SET match_score = ? WHERE id = ?",
                (score, job_id),
            )

    def get_last_scrape_timestamp(self, channel_id: str) -> str | None:
        """Get timestamp of last scraped message for incremental scraping."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT last_message_ts FROM scrape_history
                WHERE channel_id = ?
                ORDER BY scraped_at DESC
                LIMIT 1
                """,
                (channel_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def record_scrape(
        self,
        channel_id: str,
        workspace: str | None,
        last_message_ts: str,
        messages_processed: int,
        jobs_found: int,
    ) -> None:
        """Record a scrape run for incremental fetching."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO scrape_history
                (channel_id, workspace, last_message_ts, messages_processed, jobs_found)
                VALUES (?, ?, ?, ?, ?)
                """,
                (channel_id, workspace, last_message_ts, messages_processed, jobs_found),
            )

    def job_exists(self, message_ts: str, channel_id: str) -> bool:
        """Check if a job already exists in the database."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM slack_jobs WHERE message_ts = ? AND channel_id = ?",
                (message_ts, channel_id),
            )
            return cursor.fetchone() is not None

    def _row_to_job(self, row: sqlite3.Row) -> SlackJobPosting:
        """Convert a database row to a SlackJobPosting model."""
        from jobscan.models.slack import SlackJobPosting

        skills = []
        if row["skills_mentioned"]:
            try:
                skills = json.loads(row["skills_mentioned"])
            except json.JSONDecodeError:
                skills = []

        return SlackJobPosting(
            id=row["id"],
            message_ts=row["message_ts"],
            channel_id=row["channel_id"],
            channel_name=row["channel_name"],
            workspace=row["workspace"],
            posted_by_user_id=row["posted_by_user_id"],
            posted_at=row["posted_at"],
            company=row["company"],
            position=row["position"],
            location=row["location"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            salary_currency=row["salary_currency"] or "USD",
            employment_type=row["employment_type"],
            work_mode=row["work_mode"],
            raw_message=row["raw_message"],
            parsed_description=row["parsed_description"],
            job_url=row["job_url"],
            scraped_description=row["scraped_description"],
            skills=skills,
            created_at=row["created_at"],
            applied=bool(row["applied"]),
            applied_at=row["applied_at"],
            match_score=row["match_score"],
        )
