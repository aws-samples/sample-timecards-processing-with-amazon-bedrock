#!/usr/bin/env python3
"""
Database models and management for timecard processing system
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Job:
    id: str
    type: str
    status: JobStatus
    priority: JobPriority
    file_name: str
    file_size: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self):
        data = asdict(self)
        # Convert datetime objects to ISO strings
        for field in ["created_at", "updated_at", "started_at", "completed_at"]:
            if data[field]:
                data[field] = data[field].isoformat()
        # Convert enums to values
        data["status"] = self.status.value
        data["priority"] = self.priority.value
        return data


class DatabaseManager:
    def __init__(self, db_path: str = "timecard_processor.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    progress INTEGER DEFAULT 0,
                    result TEXT,
                    error TEXT,
                    metadata TEXT
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)
            """
            )

            conn.commit()

    def create_job(
        self,
        job_type: str,
        file_name: str,
        file_size: int,
        priority: JobPriority = JobPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new job"""
        import uuid

        job_id = str(uuid.uuid4())
        now = datetime.utcnow()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, type, status, priority, file_name, file_size,
                    created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    job_id,
                    job_type,
                    JobStatus.PENDING.value,
                    priority.value,
                    file_name,
                    file_size,
                    now.isoformat(),
                    now.isoformat(),
                    json.dumps(metadata) if metadata else None,
                ),
            )
            conn.commit()

        logger.info(f"Created job {job_id}: {job_type}")
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_job(row)

    def get_all_jobs(
        self, limit: int = 50, status_filter: List[str] = None
    ) -> List[Job]:
        """Get all jobs with optional filtering"""
        query = "SELECT * FROM jobs"
        params = []

        if status_filter:
            placeholders = ",".join("?" * len(status_filter))
            query += f" WHERE status IN ({placeholders})"
            params.extend(status_filter)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            return [self._row_to_job(row) for row in rows]

    def get_next_job(self) -> Optional[Job]:
        """Get next pending job by priority"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM jobs 
                WHERE status = ? 
                ORDER BY priority DESC, created_at ASC 
                LIMIT 1
            """,
                (JobStatus.PENDING.value,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_job(row)

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Update job status and related fields"""
        now = datetime.utcnow()

        with sqlite3.connect(self.db_path) as conn:
            # Build update query dynamically
            updates = ["status = ?", "updated_at = ?"]
            params = [status.value, now.isoformat()]

            if progress is not None:
                updates.append("progress = ?")
                params.append(progress)

            if result is not None:
                updates.append("result = ?")
                params.append(json.dumps(result))

            if error is not None:
                updates.append("error = ?")
                params.append(error)

            # Set timestamps based on status
            if status == JobStatus.PROCESSING:
                updates.append("started_at = ?")
                params.append(now.isoformat())
            elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                updates.append("completed_at = ?")
                params.append(now.isoformat())

            query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"
            params.append(job_id)

            conn.execute(query, params)
            conn.commit()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
                (
                    JobStatus.CANCELLED.value,
                    datetime.utcnow().isoformat(),
                    job_id,
                    JobStatus.PENDING.value,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_job(self, job_id: str) -> bool:
        """Delete a job from database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_queue_stats(self) -> Dict[str, int]:
        """Get queue statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count 
                FROM jobs 
                GROUP BY status
            """
            )
            rows = cursor.fetchall()

            stats = {status.value: 0 for status in JobStatus}
            for status, count in rows:
                stats[status] = count

            # Count jobs requiring human review (not yet completed)
            cursor = conn.execute(
                """
                SELECT COUNT(*) as review_count
                FROM jobs 
                WHERE status = 'completed' 
                AND result IS NOT NULL 
                AND json_extract(result, '$.validation.requires_human_review') = 1
                AND (json_extract(result, '$.validation.review_completed') IS NULL 
                     OR json_extract(result, '$.validation.review_completed') = 0)
            """
            )
            review_count = cursor.fetchone()[0]
            stats['review_queue'] = review_count

            return stats

    def cleanup_old_jobs(self, days: int = 7):
        """Clean up old completed jobs"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM jobs 
                WHERE status IN (?, ?, ?) 
                AND completed_at < ?
            """,
                (
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                    JobStatus.CANCELLED.value,
                    cutoff_date.isoformat(),
                ),
            )
            conn.commit()

            logger.info(f"Cleaned up {cursor.rowcount} old jobs")
            return cursor.rowcount

    def _row_to_job(self, row) -> Job:
        """Convert database row to Job object"""
        return Job(
            id=row["id"],
            type=row["type"],
            status=JobStatus(row["status"]),
            priority=JobPriority(row["priority"]),
            file_name=row["file_name"],
            file_size=row["file_size"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            started_at=(
                datetime.fromisoformat(row["started_at"]) if row["started_at"] else None
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            progress=row["progress"],
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
        )

    # Settings management
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()

            if not row:
                return default

            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return row[0]

    def set_setting(self, key: str, value: Any):
        """Set a setting value"""
        now = datetime.utcnow().isoformat()
        json_value = json.dumps(value) if not isinstance(value, str) else value

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            """,
                (key, json_value, now),
            )
            conn.commit()

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT key, value FROM settings")
            rows = cursor.fetchall()

            settings = {}
            for key, value in rows:
                try:
                    settings[key] = json.loads(value)
                except json.JSONDecodeError:
                    settings[key] = value

            return settings
