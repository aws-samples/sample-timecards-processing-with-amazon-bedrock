#!/usr/bin/env python3
"""
SQLAlchemy-based database models and management for timecard processing system
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    DateTime,
    Text,
    JSON,
    BigInteger,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import func, and_, or_
import uuid

logger = logging.getLogger(__name__)

Base = declarative_base()


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


class JobModel(Base):
    """SQLAlchemy Job model"""

    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)
    priority = Column(Integer, nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    progress = Column(Integer, default=0)
    result = Column(JSON)  # Automatically handles SQLite TEXT vs PostgreSQL JSONB
    error = Column(Text)
    job_metadata = Column("metadata", JSON)  # Use different attribute name


class SettingsModel(Base):
    """SQLAlchemy Settings model"""

    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


@dataclass
class Job:
    """Job dataclass for API responses"""

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
        # Convert datetime objects to ISO strings with UTC timezone
        for field in ["created_at", "updated_at", "started_at", "completed_at"]:
            if data[field]:
                dt = data[field]
                # Ensure datetime is timezone-aware (assume UTC if naive)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                data[field] = dt.isoformat()
        # Convert enums to values
        data["status"] = self.status.value
        data["priority"] = self.priority.value
        return data


class DatabaseManager:
    """SQLAlchemy-based database manager"""

    def __init__(self, db_url: str = None):
        if not db_url:
            # Ensure database is created in backend directory
            db_path = os.path.join(os.path.dirname(__file__), "timecard_processor.db")
            db_url = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")

        self.engine = create_engine(
            db_url,
            echo=False,  # Set to True for SQL debugging
            pool_pre_ping=True,  # Verify connections before use
        )

        # Create tables
        Base.metadata.create_all(self.engine)

        # Create session factory
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Log database type and set compatibility flag
        self.use_postgres = "postgresql" in db_url.lower()
        if self.use_postgres:
            logger.info("Using PostgreSQL database")
        else:
            logger.info("Using SQLite database")

    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()

    def create_job(
        self,
        job_type: str,
        file_name: str,
        file_size: int,
        priority: JobPriority = JobPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new job"""
        try:
            with self.get_session() as session:
                job = JobModel(
                    type=job_type,
                    status=JobStatus.PENDING.value,
                    priority=priority.value,
                    file_name=file_name,
                    file_size=file_size,
                    job_metadata=metadata,
                )
                session.add(job)
                session.commit()

                logger.info(f"Created job {job.id}: {job_type}")
                return job.id
        except Exception as e:
            logger.error(f"DatabaseManager.create_job() failed: {e}")
            raise

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        try:
            with self.get_session() as session:
                job_model = (
                    session.query(JobModel).filter(JobModel.id == job_id).first()
                )
                return self._model_to_job(job_model) if job_model else None
        except Exception as e:
            logger.error(f"DatabaseManager.get_job({job_id}) failed: {e}")
            raise

    def get_all_jobs(
        self, limit: int = 50, status_filter: List[str] = None
    ) -> List[Job]:
        """Get all jobs with optional filtering"""
        try:
            with self.get_session() as session:
                query = session.query(JobModel)

                if status_filter:
                    query = query.filter(JobModel.status.in_(status_filter))

                query = query.order_by(JobModel.created_at.desc()).limit(limit)
                job_models = query.all()

                return [self._model_to_job(job_model) for job_model in job_models]
        except Exception as e:
            logger.error(f"DatabaseManager.get_all_jobs() failed: {e}")
            logger.error(f"Parameters: limit={limit}, status_filter={status_filter}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return []

    def get_next_job(self) -> Optional[Job]:
        """Get next pending job by priority and atomically mark it as processing"""
        try:
            with self.get_session() as session:
                # Find and update in one transaction
                job_model = (
                    session.query(JobModel)
                    .filter(JobModel.status == JobStatus.PENDING.value)
                    .order_by(JobModel.priority.desc(), JobModel.created_at.asc())
                    .with_for_update(
                        skip_locked=True
                    )  # PostgreSQL skip locked, SQLite will ignore
                    .first()
                )

                if job_model:
                    now = datetime.now(timezone.utc)
                    job_model.status = JobStatus.PROCESSING.value
                    job_model.updated_at = now
                    job_model.started_at = now
                    session.commit()

                    return self._model_to_job(job_model)

                return None
        except Exception as e:
            logger.error(f"DatabaseManager.get_next_job() failed: {e}")
            raise

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Update job status and related fields"""
        try:
            with self.get_session() as session:
                job_model = (
                    session.query(JobModel).filter(JobModel.id == job_id).first()
                )

                if not job_model:
                    raise ValueError(f"Job {job_id} not found")

                now = datetime.now(timezone.utc)
                job_model.status = status.value
                job_model.updated_at = now

                if progress is not None:
                    job_model.progress = progress

                if result is not None:
                    job_model.result = result

                if error is not None:
                    job_model.error = error

                # Set timestamps based on status
                if status == JobStatus.PROCESSING and not job_model.started_at:
                    job_model.started_at = now
                elif status in [
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                ]:
                    job_model.completed_at = now

                session.commit()
        except Exception as e:
            logger.error(f"DatabaseManager.update_job_status({job_id}) failed: {e}")
            raise

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job"""
        try:
            with self.get_session() as session:
                result = (
                    session.query(JobModel)
                    .filter(
                        and_(
                            JobModel.id == job_id,
                            JobModel.status == JobStatus.PENDING.value,
                        )
                    )
                    .update(
                        {
                            "status": JobStatus.CANCELLED.value,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    )
                )
                session.commit()
                return result > 0
        except Exception as e:
            logger.error(f"DatabaseManager.cancel_job({job_id}) failed: {e}")
            raise

    def delete_job(self, job_id: str) -> bool:
        """Delete a job from database"""
        try:
            with self.get_session() as session:
                result = session.query(JobModel).filter(JobModel.id == job_id).delete()
                session.commit()
                return result > 0
        except Exception as e:
            logger.error(f"DatabaseManager.delete_job({job_id}) failed: {e}")
            raise

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics with enhanced metrics"""
        try:
            with self.get_session() as session:
                # Basic status counts
                status_counts = (
                    session.query(JobModel.status, func.count(JobModel.id))
                    .group_by(JobModel.status)
                    .all()
                )

                stats = {status.value: 0 for status in JobStatus}
                for status, count in status_counts:
                    stats[status] = count

                # Review queue count - simplified for now (will implement properly later)
                # This is complex with cross-database JSON queries, so we'll use Python filtering
                completed_jobs = (
                    session.query(JobModel)
                    .filter(
                        and_(
                            JobModel.status == JobStatus.COMPLETED.value,
                            JobModel.result.isnot(None),
                        )
                    )
                    .all()
                )

                review_count = 0
                for job in completed_jobs:
                    if (
                        job.result
                        and isinstance(job.result, dict)
                        and job.result.get("validation", {}).get(
                            "requires_human_review"
                        )
                        and not job.result.get("validation", {}).get(
                            "review_completed", False
                        )
                    ):
                        review_count += 1

                stats["review_queue"] = review_count

                # Calculate total jobs
                stats["total_jobs"] = sum(stats[status.value] for status in JobStatus)

                # Calculate average processing time for completed jobs
                # Use Python calculation instead of SQL for cross-database compatibility
                completed_jobs_with_times = (
                    session.query(JobModel.started_at, JobModel.completed_at)
                    .filter(
                        and_(
                            JobModel.status == JobStatus.COMPLETED.value,
                            JobModel.started_at.isnot(None),
                            JobModel.completed_at.isnot(None),
                        )
                    )
                    .all()
                )

                if completed_jobs_with_times:
                    total_time = 0
                    valid_jobs = 0
                    for started_at, completed_at in completed_jobs_with_times:
                        if started_at and completed_at and completed_at > started_at:
                            duration = (completed_at - started_at).total_seconds()
                            if duration > 0:  # Only count positive durations
                                total_time += duration
                                valid_jobs += 1

                    avg_time = total_time / valid_jobs if valid_jobs > 0 else 0
                else:
                    avg_time = 0

                stats["avg_processing_time"] = round(avg_time, 2)

                # Success rate
                total_finished = stats["completed"] + stats["failed"]
                stats["success_rate"] = (
                    (stats["completed"] / total_finished * 100)
                    if total_finished > 0
                    else 0
                )

                # Jobs created today
                today_count = (
                    session.query(func.count(JobModel.id))
                    .filter(func.date(JobModel.created_at) == func.current_date())
                    .scalar()
                    or 0
                )
                stats["jobs_today"] = today_count

                return stats
        except Exception as e:
            logger.error(f"DatabaseManager.get_queue_stats() failed: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Return empty stats instead of crashing
            return {status.value: 0 for status in JobStatus}

    def cleanup_old_jobs(self, days: int = 7):
        """Clean up old completed jobs"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            with self.get_session() as session:
                result = (
                    session.query(JobModel)
                    .filter(
                        and_(
                            JobModel.status.in_(
                                [
                                    JobStatus.COMPLETED.value,
                                    JobStatus.FAILED.value,
                                    JobStatus.CANCELLED.value,
                                ]
                            ),
                            JobModel.completed_at < cutoff_date,
                        )
                    )
                    .delete()
                )
                session.commit()

                logger.info(f"Cleaned up {result} old jobs")
                return result
        except Exception as e:
            logger.error(f"DatabaseManager.cleanup_old_jobs() failed: {e}")
            raise

    def _model_to_job(self, job_model: JobModel) -> Job:
        """Convert SQLAlchemy model to Job dataclass"""
        return Job(
            id=job_model.id,
            type=job_model.type,
            status=JobStatus(job_model.status),
            priority=JobPriority(job_model.priority),
            file_name=job_model.file_name,
            file_size=job_model.file_size,
            created_at=job_model.created_at,
            updated_at=job_model.updated_at,
            started_at=job_model.started_at,
            completed_at=job_model.completed_at,
            progress=job_model.progress,
            result=job_model.result,
            error=job_model.error,
            metadata=job_model.job_metadata,
        )

    # Settings management
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        try:
            with self.get_session() as session:
                setting = (
                    session.query(SettingsModel)
                    .filter(SettingsModel.key == key)
                    .first()
                )
                return setting.value if setting else default
        except Exception as e:
            logger.error(f"DatabaseManager.get_setting({key}) failed: {e}")
            return default

    def set_setting(self, key: str, value: Any):
        """Set a setting value"""
        try:
            with self.get_session() as session:
                setting = (
                    session.query(SettingsModel)
                    .filter(SettingsModel.key == key)
                    .first()
                )

                if setting:
                    setting.value = value
                    setting.updated_at = datetime.now(timezone.utc)
                else:
                    setting = SettingsModel(key=key, value=value)
                    session.add(setting)

                session.commit()
        except Exception as e:
            logger.error(f"DatabaseManager.set_setting({key}) failed: {e}")
            raise

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings"""
        try:
            with self.get_session() as session:
                settings = session.query(SettingsModel).all()
                return {setting.key: setting.value for setting in settings}
        except Exception as e:
            logger.error(f"DatabaseManager.get_all_settings() failed: {e}")
            return {}
