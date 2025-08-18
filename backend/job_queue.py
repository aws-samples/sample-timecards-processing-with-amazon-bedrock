#!/usr/bin/env python3
"""
Job Queue Management System - Database-backed implementation
Handles job creation, status tracking, and queue operations
"""

import logging
from typing import List, Optional, Dict, Any
from database import DatabaseManager, Job, JobStatus, JobPriority

logger = logging.getLogger(__name__)


class JobQueue:
    """Database-backed job queue"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create_job(
        self,
        job_type: str,
        file_name: str,
        file_size: int,
        priority: JobPriority = JobPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new job and add it to the queue"""
        return self.db.create_job(job_type, file_name, file_size, priority, metadata)

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        return self.db.get_job(job_id)

    def get_all_jobs(
        self, limit: int = 50, status_filter: List[str] = None
    ) -> List[Job]:
        """Get all jobs with optional filtering"""
        return self.db.get_all_jobs(limit, status_filter)

    def get_next_job(self) -> Optional[Job]:
        """Get the next pending job by priority"""
        return self.db.get_next_job()

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Update job status and related fields"""
        self.db.update_job_status(job_id, status, progress, result, error)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job"""
        return self.db.cancel_job(job_id)

    def delete_job(self, job_id: str) -> bool:
        """Delete a job"""
        return self.db.delete_job(job_id)

    def get_queue_stats(self) -> Dict[str, int]:
        """Get queue statistics"""
        return self.db.get_queue_stats()

    def cleanup_old_jobs(self, days: int = 7) -> int:
        """Clean up old completed jobs"""
        return self.db.cleanup_old_jobs(days)
