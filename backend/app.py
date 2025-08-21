#!/usr/bin/env python3
"""
Flask API for Cast & Crew Timecard Processing
Stateless Job Queue System with SQLite persistence
"""

import os
import json
import logging
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from timecard_pipeline import TimecardPipeline
from database import DatabaseManager, JobStatus, JobPriority
from job_queue import JobQueue
from config_manager import ConfigManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app, origins=["http://localhost:3000", "http://127.0.0.1:3000"])

# Initialize database and configuration
try:
    db_manager = DatabaseManager()
    config_manager = ConfigManager(db_manager)
    job_queue = JobQueue(db_manager)
    logger.info("Database and configuration initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    raise

# Configuration
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Initialize pipeline with configuration
try:
    pipeline = TimecardPipeline(config_manager)
    logger.info("Pipeline initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize pipeline: {e}")
    # Create a fallback pipeline without config
    pipeline = TimecardPipeline()


# Initialize Automated Reasoning (non-blocking, only if not configured)
def init_automated_reasoning():
    """Initialize Automated Reasoning in background thread"""
    try:
        from automated_reasoning_provisioner import AutomatedReasoningProvisioner

        provisioner = AutomatedReasoningProvisioner(
            region_name=config_manager.aws_region, config_manager=config_manager
        )

        current_status = config_manager.get(
            "automated_reasoning_status", "not_configured"
        )
        logger.info(
            f"Automated Reasoning initialization - current status: {current_status}"
        )

        if current_status == "not_configured":
            logger.info("Starting initial Automated Reasoning setup...")
            provisioner.ensure_provisioned()
        elif current_status == "creating":
            logger.info(
                "Automated Reasoning creation in progress, checking if completed..."
            )
            # Check if creation is actually completed but DB wasn't updated
            policy_arn = config_manager.get("automated_reasoning_policy_arn")
            build_workflow_id = config_manager.get(
                "automated_reasoning_build_workflow_id"
            )

            if policy_arn and build_workflow_id:
                try:
                    # Check if build workflow is completed
                    result = provisioner._check_creation_progress(
                        policy_arn, build_workflow_id
                    )
                    new_status = result.get("status", "creating")
                    logger.info(f"Creation progress check result: {new_status}")

                    if new_status == "ready":
                        logger.info("Creation was completed, DB updated to ready")
                    elif new_status == "failed":
                        logger.warning("Creation failed, will need manual retry")
                    else:
                        logger.info("Creation still in progress")
                except Exception as e:
                    logger.error(f"Failed to check creation progress during init: {e}")
            else:
                logger.warning(
                    "Creating status but missing policy ARN or build workflow ID"
                )
        elif current_status == "ready":
            logger.info("Automated Reasoning already ready")
            # Verify resources still exist, but don't recreate automatically
            try:
                policy_arn = config_manager.get("automated_reasoning_policy_arn")
                guardrail_id = config_manager.get("automated_reasoning_guardrail_id")

                if policy_arn and guardrail_id:
                    policy_exists, guardrail_exists = (
                        provisioner._check_existing_resources()
                    )
                    if policy_exists and guardrail_exists:
                        logger.info("Automated Reasoning resources verified and ready")
                    else:
                        logger.warning(
                            "Some resources missing, but keeping ready status (manual intervention may be needed)"
                        )
                else:
                    logger.warning("Missing policy ARN or guardrail ID in ready state")
            except Exception as e:
                logger.error(f"Failed to verify existing resources: {e}")
        else:
            logger.info(
                f"Automated Reasoning in {current_status} state, no action needed"
            )

    except Exception as e:
        logger.error(f"Failed to initialize Automated Reasoning: {e}")


# Start Automated Reasoning initialization in background thread
import threading

ar_init_thread = threading.Thread(target=init_automated_reasoning, daemon=True)
ar_init_thread.start()


# Background job processor
def job_processor():
    """Background thread to process jobs"""
    max_concurrent = config_manager.max_concurrent_jobs
    active_jobs = {}

    while True:
        try:
            # Check if we can process more jobs
            if len(active_jobs) >= max_concurrent:
                time.sleep(1)
                continue

            job = job_queue.get_next_job()
            if not job:
                time.sleep(0.5)  # Wait 0.5 seconds before checking again
                continue

            logger.info(f"Processing job {job.id}: {job.type}")

            # Job is already marked as processing by get_next_job()
            active_jobs[job.id] = job

            # Process job in separate thread
            def process_job(job):
                try:
                    if job.type == "timecard_processing":
                        # Get file path from metadata
                        file_path = (
                            job.metadata.get("file_path") if job.metadata else None
                        )
                        if not file_path or not Path(file_path).exists():
                            raise Exception("File not found")

                        # Update progress - Step 1: Excel to Markdown
                        job_queue.update_job_status(
                            job.id, JobStatus.PROCESSING, progress=10
                        )

                        # Process through pipeline
                        result = pipeline.process(file_path)

                        # Update progress - Almost complete
                        job_queue.update_job_status(
                            job.id, JobStatus.PROCESSING, progress=90
                        )

                        # Clean up uploaded file (only if not a sample)
                        is_sample = (
                            job.metadata.get("is_sample", False)
                            if job.metadata
                            else False
                        )
                        if not is_sample:
                            try:
                                Path(file_path).unlink()
                            except:
                                pass

                        # Complete job
                        job_queue.update_job_status(
                            job.id, JobStatus.COMPLETED, progress=100, result=result
                        )

                        logger.info(f"Job {job.id} completed successfully")

                    else:
                        raise Exception(f"Unknown job type: {job.type}")

                except Exception as e:
                    logger.error(f"Job {job.id} failed: {e}")
                    job_queue.update_job_status(job.id, JobStatus.FAILED, error=str(e))
                finally:
                    # Remove from active jobs
                    if job.id in active_jobs:
                        del active_jobs[job.id]

            # Start processing thread
            thread = threading.Thread(target=process_job, args=(job,), daemon=True)
            thread.start()

        except Exception as e:
            logger.error(f"Job processor error: {e}")
            time.sleep(5)


# Start background job processor
processor_thread = threading.Thread(target=job_processor, daemon=True)
processor_thread.start()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        stats = job_queue.get_queue_stats()

        # Test if we're using PostgreSQL or SQLite
        db_type = "postgresql" if db_manager.use_postgres else "sqlite"

        # Get Automated Reasoning status
        ar_status = config_manager.get("automated_reasoning_status", "not_configured")
        ar_guardrail_id = config_manager.get("automated_reasoning_guardrail_id")

        validation_method = (
            "automated_reasoning"
            if ar_status == "ready" and ar_guardrail_id
            else "fallback"
        )

        return jsonify(
            {
                "status": "healthy",
                "service": "timecard-processor",
                "database": db_type,
                "queue_stats": stats,
                "automated_reasoning": {
                    "status": ar_status,
                    "validation_method": validation_method,
                    "guardrail_active": bool(ar_guardrail_id and ar_status == "ready"),
                },
            }
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return (
            jsonify(
                {"status": "error", "service": "timecard-processor", "error": str(e)}
            ),
            500,
        )


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Upload file and create processing job"""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        if not allowed_file(file.filename):
            return (
                jsonify({"error": "Invalid file type. Only Excel files allowed"}),
                400,
            )

        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = int(time.time())
        unique_filename = f"{timestamp}_{filename}"
        file_path = UPLOAD_FOLDER / unique_filename
        file.save(file_path)

        # Get file size
        file_size = file_path.stat().st_size

        logger.info(f"File uploaded: {filename} ({file_size} bytes)")

        # Create job with model information
        job_id = job_queue.create_job(
            job_type="timecard_processing",
            file_name=filename,
            file_size=file_size,
            priority=JobPriority.NORMAL,
            metadata={
                "file_path": str(file_path),
                "original_filename": filename,
                "model_info": {
                    "model_id": config_manager.bedrock_model_id,
                    "aws_region": config_manager.aws_region,
                },
            },
        )

        return jsonify(
            {
                "status": "success",
                "job_id": job_id,
                "message": "File uploaded and job created",
                "file_name": filename,
                "file_size": file_size,
            }
        )

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/<job_id>/download", methods=["GET"])
def download_job_file(job_id):
    """Download the original file for a job"""
    try:
        job = job_queue.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Get file path from metadata
        file_path = job.metadata.get("file_path") if job.metadata else None
        if not file_path:
            return jsonify({"error": "File path not found in job metadata"}), 404

        file_path = Path(file_path)

        # Check if file exists
        if not file_path.exists():
            return jsonify({"error": "File not found on server"}), 404

        # Get original filename from job
        original_filename = job.file_name or file_path.name

        # Send file for download
        return send_from_directory(
            file_path.parent,
            file_path.name,
            as_attachment=True,
            download_name=original_filename,
        )

    except Exception as e:
        logger.error(f"Failed to download file for job {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    """Get all jobs with optional filtering"""
    try:
        # Get query parameters
        limit = int(request.args.get("limit", 50))
        status_filter = request.args.getlist("status")

        jobs = job_queue.get_all_jobs(limit=limit, status_filter=status_filter)

        return jsonify({"jobs": [job.to_dict() for job in jobs], "count": len(jobs)})

    except Exception as e:
        import traceback

        logger.error(f"API /api/jobs failed: {e}")
        logger.error(f"Function: get_jobs()")
        logger.error(
            f"Parameters: limit={request.args.get('limit', 50)}, status_filter={request.args.getlist('status')}"
        )
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return (
            jsonify({"error": str(e), "function": "get_jobs", "endpoint": "/api/jobs"}),
            500,
        )


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    """Get specific job by ID"""
    try:
        job = job_queue.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify(job.to_dict())

    except Exception as e:
        import traceback

        logger.error(f"API /api/jobs/{job_id} failed: {e}")
        logger.error(f"Function: get_job()")
        logger.error(f"Job ID: {job_id}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return (
            jsonify(
                {
                    "error": str(e),
                    "function": "get_job",
                    "endpoint": f"/api/jobs/{job_id}",
                    "job_id": job_id,
                }
            ),
            500,
        )


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    """Cancel a pending job"""
    try:
        success = job_queue.cancel_job(job_id)
        if not success:
            return jsonify({"error": "Job not found or cannot be cancelled"}), 400

        return jsonify({"status": "success", "message": "Job cancelled"})

    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/<job_id>/stop", methods=["POST"])
def stop_job(job_id):
    """Stop a processing job"""
    try:
        job = job_queue.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        if job.status.value not in ["processing"]:
            return (
                jsonify({"error": f"Job is {job.status.value}, cannot be stopped"}),
                400,
            )

        # Update job status to cancelled
        job_queue.update_job_status(
            job_id, JobStatus.CANCELLED, error="Job stopped by user"
        )

        logger.info(f"Job {job_id} stopped by user")
        return jsonify({"status": "success", "message": "Job stopped"})

    except Exception as e:
        logger.error(f"Failed to stop job {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    """Delete a job (completed, failed, or cancelled jobs only)"""
    try:
        job = job_queue.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        if job.status.value in ["pending", "processing"]:
            return (
                jsonify(
                    {
                        "error": f"Cannot delete {job.status.value} job. Stop or cancel it first."
                    }
                ),
                400,
            )

        # Delete job from database
        success = job_queue.delete_job(job_id)
        if not success:
            return jsonify({"error": "Failed to delete job"}), 500

        logger.info(f"Job {job_id} deleted by user")
        return jsonify({"status": "success", "message": "Job deleted"})

    except Exception as e:
        logger.error(f"Failed to delete job {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/bulk-delete", methods=["POST"])
def bulk_delete_jobs():
    """Delete multiple jobs (completed, failed, or cancelled jobs only)"""
    try:
        data = request.get_json()
        if not data or "job_ids" not in data:
            return jsonify({"error": "job_ids is required"}), 400

        job_ids = data["job_ids"]
        if not isinstance(job_ids, list) or len(job_ids) == 0:
            return jsonify({"error": "job_ids must be a non-empty array"}), 400

        deleted_count = 0
        errors = []

        for job_id in job_ids:
            try:
                job = job_queue.get_job(job_id)
                if not job:
                    errors.append(f"Job {job_id} not found")
                    continue

                if job.status.value in ["pending", "processing"]:
                    errors.append(f"Cannot delete {job.status.value} job {job_id}")
                    continue

                success = job_queue.delete_job(job_id)
                if success:
                    deleted_count += 1
                    logger.info(f"Job {job_id} deleted by user")
                else:
                    errors.append(f"Failed to delete job {job_id}")

            except Exception as e:
                errors.append(f"Error deleting job {job_id}: {str(e)}")

        response = {
            "status": "success",
            "deleted_count": deleted_count,
            "total_requested": len(job_ids),
        }

        if errors:
            response["errors"] = errors
            response["message"] = (
                f"Deleted {deleted_count} of {len(job_ids)} jobs with {len(errors)} errors"
            )
        else:
            response["message"] = f"Successfully deleted {deleted_count} jobs"

        return jsonify(response)

    except Exception as e:
        logger.error(f"Failed to bulk delete jobs: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/queue/stats", methods=["GET"])
def get_queue_stats():
    """Get queue statistics"""
    try:
        stats = job_queue.get_queue_stats()
        return jsonify(stats)

    except Exception as e:
        import traceback

        logger.error(f"API /api/queue/stats failed: {e}")
        logger.error(f"Function: get_queue_stats()")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return (
            jsonify(
                {
                    "error": str(e),
                    "function": "get_queue_stats",
                    "endpoint": "/api/queue/stats",
                }
            ),
            500,
        )


@app.route("/api/review-queue", methods=["GET"])
def get_review_queue():
    """Get pending review items from completed jobs that require human review"""
    try:
        # Get completed jobs that require human review
        completed_jobs = job_queue.get_all_jobs(status_filter=["completed"])
        review_items = []

        for job in completed_jobs:
            if (
                job.result
                and isinstance(job.result, dict)
                and job.result.get("validation", {}).get("requires_human_review")
                and not job.result.get("validation", {}).get("review_completed", False)
            ):

                validation = job.result.get("validation", {})
                extracted_data = job.result.get("extracted_data", {})

                try:
                    # Safe datetime conversion
                    created_at_str = None
                    if job.created_at:
                        if hasattr(job.created_at, "isoformat"):
                            created_at_str = job.created_at.isoformat()
                        else:
                            created_at_str = str(job.created_at)

                    review_item = {
                        "id": f"review_{job.id}",
                        "job_id": job.id,
                        "file_name": job.file_name or "Unknown File",
                        "employee_name": validation.get("employee_name")
                        or extracted_data.get("employee_name", "Unknown"),
                        "validation_result": validation.get(
                            "validation_result", "REQUIRES_HUMAN_REVIEW"
                        ),
                        "validation_issues": validation.get("validation_issues", []),
                        "total_wage": validation.get("total_wage", 0),
                        "average_daily_rate": validation.get("average_daily_rate", 0),
                        "total_days": validation.get("total_days", 0),
                        "unique_days": extracted_data.get(
                            "unique_days", validation.get("total_days", 0)
                        ),
                        "created_at": created_at_str,
                        "status": "pending",
                    }
                except Exception as item_error:
                    logger.error(
                        f"Error creating review item for job {job.id}: {item_error}"
                    )
                    continue
                review_items.append(review_item)

        # Sort by creation date (newest first) - use job.created_at for sorting before conversion
        review_items.sort(key=lambda x: x.get("created_at") or "", reverse=True)

        return jsonify({"review_queue": review_items, "count": len(review_items)})
    except Exception as e:
        import traceback

        logger.error(f"API /api/review-queue failed: {e}")
        logger.error(f"Function: get_review_queue()")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return (
            jsonify(
                {
                    "error": str(e),
                    "function": "get_review_queue",
                    "endpoint": "/api/review-queue",
                }
            ),
            500,
        )


@app.route("/api/jobs/<job_id>/complete-review", methods=["POST"])
def complete_review(job_id):
    """Mark a job's review as completed"""
    try:
        job = job_queue.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        if not (
            job.result
            and isinstance(job.result, dict)
            and job.result.get("validation", {}).get("requires_human_review")
        ):
            return jsonify({"error": "Job does not require human review"}), 400

        # Update the job result to mark review as completed
        updated_result = job.result.copy()
        if "validation" not in updated_result:
            updated_result["validation"] = {}

        updated_result["validation"]["review_completed"] = True
        updated_result["validation"]["review_completed_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        updated_result["validation"]["validation_result"] = "REVIEWED"

        # Update job in database
        job_queue.update_job_status(job_id, JobStatus.COMPLETED, result=updated_result)

        logger.info(f"Review completed for job {job_id}")

        return jsonify(
            {"status": "success", "message": "Review completed successfully"}
        )

    except Exception as e:
        import traceback

        logger.error(f"API /api/jobs/{job_id}/complete-review failed: {e}")
        logger.error(f"Function: complete_review()")
        logger.error(f"Job ID: {job_id}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return (
            jsonify(
                {
                    "error": str(e),
                    "function": "complete_review",
                    "endpoint": f"/api/jobs/{job_id}/complete-review",
                    "job_id": job_id,
                }
            ),
            500,
        )


@app.route("/api/jobs/bulk-complete-review", methods=["POST"])
def bulk_complete_review():
    """Mark multiple jobs' reviews as completed"""
    try:
        data = request.get_json()
        if not data or "job_ids" not in data:
            return jsonify({"error": "job_ids is required"}), 400

        job_ids = data["job_ids"]
        if not isinstance(job_ids, list) or len(job_ids) == 0:
            return jsonify({"error": "job_ids must be a non-empty array"}), 400

        completed_count = 0
        errors = []

        for job_id in job_ids:
            try:
                job = job_queue.get_job(job_id)
                if not job:
                    errors.append(f"Job {job_id} not found")
                    continue

                if not (
                    job.result
                    and isinstance(job.result, dict)
                    and job.result.get("validation", {}).get("requires_human_review")
                ):
                    errors.append(f"Job {job_id} does not require human review")
                    continue

                # Update the job result to mark review as completed
                updated_result = job.result.copy()
                if "validation" not in updated_result:
                    updated_result["validation"] = {}

                updated_result["validation"]["review_completed"] = True
                updated_result["validation"]["review_completed_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                updated_result["validation"]["validation_result"] = "REVIEWED"

                # Update job in database
                job_queue.update_job_status(
                    job_id, JobStatus.COMPLETED, result=updated_result
                )

                completed_count += 1
                logger.info(f"Review completed for job {job_id}")

            except Exception as e:
                errors.append(f"Error completing review for job {job_id}: {str(e)}")

        response = {
            "status": "success",
            "completed_count": completed_count,
            "total_requested": len(job_ids),
        }

        if errors:
            response["errors"] = errors
            response["message"] = (
                f"Completed {completed_count} of {len(job_ids)} reviews with {len(errors)} errors"
            )
        else:
            response["message"] = f"Successfully completed {completed_count} reviews"

        return jsonify(response)

    except Exception as e:
        import traceback

        logger.error(f"API /api/jobs/bulk-complete-review failed: {e}")
        logger.error(f"Function: bulk_complete_review()")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return (
            jsonify(
                {
                    "error": str(e),
                    "function": "bulk_complete_review",
                    "endpoint": "/api/jobs/bulk-complete-review",
                }
            ),
            500,
        )


@app.route("/api/queue/cleanup", methods=["POST"])
def cleanup_queue():
    """Clean up old completed jobs"""
    try:
        data = request.get_json() or {}
        days = int(data.get("days", config_manager.cleanup_after_days))
        count = job_queue.cleanup_old_jobs(days)
        return jsonify(
            {
                "status": "success",
                "message": f"Cleaned up {count} jobs older than {days} days",
                "count": count,
            }
        )

    except Exception as e:
        logger.error(f"Failed to cleanup queue: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Get all application settings"""
    try:
        settings = config_manager.get_all()

        # Get automated reasoning status without triggering provisioning
        try:
            from automated_reasoning_provisioner import AutomatedReasoningProvisioner

            provisioner = AutomatedReasoningProvisioner(
                region_name=config_manager.aws_region, config_manager=config_manager
            )

            # Only get current status, don't trigger provisioning
            ar_result = provisioner._get_current_status_with_smart_check()

            automated_reasoning_status = {
                "status": ar_result.get("status", "unknown"),
                "policy_arn": ar_result.get("policy_arn"),
                "guardrail_id": ar_result.get("guardrail_id"),
                "guardrail_version": ar_result.get("guardrail_version"),
                "message": ar_result.get("message", ""),
                "build_status": ar_result.get("build_status"),
                "created": ar_result.get("created", False),
                "error": ar_result.get("error"),
                "validation_method": (
                    "automated_reasoning"
                    if ar_result.get("status") == "ready"
                    and ar_result.get("guardrail_id")
                    else "fallback"
                ),
            }
        except Exception as e:
            logger.error(f"Failed to get automated reasoning status: {e}")
            automated_reasoning_status = {
                "status": "error",
                "error": str(e),
                "validation_method": "fallback",
            }

        # Add system information
        settings.update(
            {
                "system_info": config_manager.get_system_info(),
                "aws_config_status": config_manager.validate_aws_config(),
                "automated_reasoning_status": automated_reasoning_status,
            }
        )

        return jsonify(settings)

    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/automated-reasoning/status", methods=["GET"])
def get_automated_reasoning_status():
    """Get current Automated Reasoning status"""
    try:
        from automated_reasoning_provisioner import AutomatedReasoningProvisioner

        provisioner = AutomatedReasoningProvisioner(
            region_name=config_manager.aws_region, config_manager=config_manager
        )

        # Non-blocking status check
        result = provisioner.ensure_provisioned()

        return jsonify(
            {
                "status": result.get("status", "unknown"),
                "policy_arn": result.get("policy_arn"),
                "guardrail_id": result.get("guardrail_id"),
                "guardrail_version": result.get("guardrail_version"),
                "message": result.get("message", ""),
                "build_status": result.get("build_status"),
                "created": result.get("created", False),
                "error": result.get("error"),
                "last_check": config_manager.get("automated_reasoning_last_check"),
                "created_at": config_manager.get("automated_reasoning_created_at"),
            }
        )

    except Exception as e:
        logger.error(f"Failed to get Automated Reasoning status: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/automated-reasoning/check-progress", methods=["POST"])
def check_automated_reasoning_progress():
    """Check Automated Reasoning setup progress (rate limited)"""
    try:
        from automated_reasoning_provisioner import AutomatedReasoningProvisioner

        provisioner = AutomatedReasoningProvisioner(
            region_name=config_manager.aws_region, config_manager=config_manager
        )

        current_status = config_manager.get(
            "automated_reasoning_status", "not_configured"
        )

        if current_status != "creating":
            return jsonify(
                {
                    "status": "success",
                    "message": f"Status is {current_status}, no progress to check",
                    "result": provisioner._get_current_status(),
                }
            )

        # Check if enough time has passed since last check
        last_check = config_manager.get("automated_reasoning_last_check", 0)
        now = time.time()

        if (now - last_check) < 10:  # Rate limit to once per 10 seconds
            return jsonify(
                {
                    "status": "rate_limited",
                    "message": f"Please wait {10 - (now - last_check):.1f} seconds before checking again",
                    "result": provisioner._get_current_status(),
                }
            )

        # Actually check progress
        policy_arn = config_manager.get("automated_reasoning_policy_arn")
        build_workflow_id = config_manager.get("automated_reasoning_build_workflow_id")

        if policy_arn and build_workflow_id:
            result = provisioner._check_creation_progress(policy_arn, build_workflow_id)
            return jsonify(
                {"status": "success", "message": "Progress checked", "result": result}
            )
        else:
            return jsonify(
                {
                    "status": "error",
                    "message": "Missing policy ARN or build workflow ID",
                    "result": provisioner._get_current_status(),
                }
            )

    except Exception as e:
        logger.error(f"Failed to check Automated Reasoning progress: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/automated-reasoning/retry", methods=["POST"])
def retry_automated_reasoning():
    """Retry Automated Reasoning setup"""
    try:
        from automated_reasoning_provisioner import AutomatedReasoningProvisioner

        provisioner = AutomatedReasoningProvisioner(
            region_name=config_manager.aws_region, config_manager=config_manager
        )

        # Force recreation
        result = provisioner.ensure_provisioned(force_recreate=True)

        return jsonify(
            {
                "status": "success",
                "message": "Automated Reasoning setup retry initiated",
                "result": result,
            }
        )

    except Exception as e:
        logger.error(f"Failed to retry Automated Reasoning setup: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/settings", methods=["POST"])
def update_settings():
    """Update application settings"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Update settings
        config_manager.update_multiple(data)

        return jsonify(
            {"status": "success", "message": "Settings updated successfully"}
        )

    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/<setting_key>", methods=["GET"])
def get_setting(setting_key):
    """Get a specific setting"""
    try:
        value = config_manager.get(setting_key)
        return jsonify({"key": setting_key, "value": value})

    except Exception as e:
        logger.error(f"Failed to get setting {setting_key}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/<setting_key>", methods=["PUT"])
def update_setting(setting_key):
    """Update a specific setting"""
    try:
        data = request.get_json()
        if not data or "value" not in data:
            return jsonify({"error": "Value is required"}), 400

        config_manager.set(setting_key, data["value"])

        return jsonify(
            {
                "status": "success",
                "message": f"Setting {setting_key} updated successfully",
            }
        )

    except Exception as e:
        logger.error(f"Failed to update setting {setting_key}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/samples")
def list_samples():
    """List available sample files"""
    try:
        samples = []
        sample_dirs = [Path("data"), Path("sample"), Path("../data"), Path("../sample")]

        for sample_dir in sample_dirs:
            if sample_dir.exists():
                samples.extend(
                    [
                        f.name
                        for f in sample_dir.glob("*.xlsx")
                        if not f.name.startswith("~$")
                    ]
                )
                samples.extend(
                    [
                        f.name
                        for f in sample_dir.glob("*.xlsm")
                        if not f.name.startswith("~$")
                    ]
                )

        samples = list(set(samples))
        return jsonify(samples)

    except Exception as e:
        logger.error(f"Error listing samples: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/process-sample/<filename>")
def process_sample(filename):
    """Process a sample Excel file as a job"""
    try:
        possible_paths = [
            Path("data") / filename,
            Path("sample") / filename,
            Path("../data") / filename,
            Path("../sample") / filename,
        ]

        sample_path = None
        for path in possible_paths:
            if path.exists():
                sample_path = path
                break

        if not sample_path:
            return jsonify({"error": f"Sample file {filename} not found"}), 404

        # Get file size
        file_size = sample_path.stat().st_size

        # Create job for sample processing
        job_id = job_queue.create_job(
            job_type="timecard_processing",
            file_name=filename,
            file_size=file_size,
            priority=JobPriority.HIGH,  # Sample files get high priority
            metadata={
                "file_path": str(sample_path),
                "original_filename": filename,
                "is_sample": True,
                "model_info": {
                    "model_id": config_manager.bedrock_model_id,
                    "aws_region": config_manager.aws_region,
                },
            },
        )

        return jsonify(
            {
                "status": "success",
                "job_id": job_id,
                "message": f"Sample file {filename} queued for processing",
                "file_name": filename,
                "file_size": file_size,
            }
        )

    except Exception as e:
        logger.error(f"Error processing sample {filename}: {e}")
        return jsonify({"error": str(e)}), 500


# Serve React App
@app.route("/app")
def serve_react_app():
    """Serve the React app"""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/app/<path:path>")
def serve_static_files(path):
    """Serve static files or fallback to React app"""
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting Timecard Processor API on http://0.0.0.0:{port}")
    logger.info(f"Frontend should connect to http://localhost:{port}/api")
    app.run(host="0.0.0.0", port=port, debug=True)
