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
from s3_utils import S3Manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(
    app,
    origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://timecard.sanghwa.people.aws.dev",
    ],
)

# Initialize database and configuration
try:
    db_manager = DatabaseManager()
    config_manager = ConfigManager(db_manager)
    job_queue = JobQueue(db_manager)
    logger.info("Database and configuration initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    raise

# Initialize S3 manager
s3_manager = None
try:
    s3_bucket = config_manager.s3_app_data_bucket
    logger.info(f"S3 bucket configuration: {s3_bucket}")
    if s3_bucket:
        s3_manager = S3Manager(s3_bucket, config_manager.aws_region)
        logger.info(f"S3 manager initialized for bucket: {s3_bucket} in region: {config_manager.aws_region}")
        
        # Test S3 access
        access_check = s3_manager.check_bucket_access()
        logger.info(f"S3 bucket access check: {access_check}")
        
        if not access_check.get('accessible', False):
            logger.error(f"S3 bucket not accessible: {access_check}")
            s3_manager = None
    else:
        logger.warning("S3 bucket not configured, falling back to local storage")
except Exception as e:
    logger.error(f"Failed to initialize S3 manager: {e}")
    logger.warning("Falling back to local storage")
    s3_manager = None

# Configuration
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"xlsx", "xls", "xlsm", "csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = (
    500 * 1024 * 1024
)  # 500MB max file size for large Excel files

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
                local_file_path = None
                try:
                    if job.type == "timecard_processing":
                        storage_type = (
                            job.metadata.get("storage_type", "local")
                            if job.metadata
                            else "local"
                        )

                        if storage_type == "s3":
                            # Handle S3 stored file
                            s3_key = job.metadata.get("s3_key")
                            s3_bucket = job.metadata.get("s3_bucket")
                            unique_filename = job.metadata.get("unique_filename")

                            logger.info(f"Processing S3 job - s3_key: {s3_key}, s3_bucket: {s3_bucket}, s3_manager: {s3_manager is not None}")
                            logger.info(f"Job metadata: {job.metadata}")

                            if not s3_key or not s3_bucket:
                                raise Exception(f"S3 file information missing - s3_key: {s3_key}, s3_bucket: {s3_bucket}")
                            
                            if not s3_manager:
                                raise Exception("S3 manager not available - check S3 configuration")

                            # Download file from S3 to temporary local path
                            temp_dir = Path("temp_processing")
                            temp_dir.mkdir(exist_ok=True)
                            local_file_path = temp_dir / unique_filename

                            logger.info(f"Downloading file from S3: {s3_key} to {local_file_path}")
                            if not s3_manager.download_file(
                                s3_key, str(local_file_path)
                            ):
                                raise Exception(f"Failed to download file from S3: {s3_key}")

                            if not local_file_path.exists():
                                raise Exception(f"Downloaded file does not exist: {local_file_path}")

                            file_path = str(local_file_path)
                            logger.info(f"S3 file downloaded successfully: {file_path} (size: {local_file_path.stat().st_size} bytes)")

                        else:
                            # Handle local file
                            file_path = (
                                job.metadata.get("file_path") if job.metadata else None
                            )
                            if not file_path or not Path(file_path).exists():
                                raise Exception("Local file not found")

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

                        # Clean up files (only if not a sample)
                        is_sample = (
                            job.metadata.get("is_sample", False)
                            if job.metadata
                            else False
                        )

                        if not is_sample:
                            if storage_type == "s3":
                                # Clean up S3 file and local temp file
                                try:
                                    if s3_manager and job.metadata.get("s3_key"):
                                        s3_manager.delete_file(job.metadata["s3_key"])
                                        logger.info(
                                            f"Deleted S3 file: {job.metadata['s3_key']}"
                                        )
                                except Exception as e:
                                    logger.warning(f"Failed to delete S3 file: {e}")

                                # Clean up local temp file
                                if local_file_path and local_file_path.exists():
                                    try:
                                        local_file_path.unlink()
                                        logger.info(
                                            f"Deleted temp file: {local_file_path}"
                                        )
                                    except Exception as e:
                                        logger.warning(
                                            f"Failed to delete temp file: {e}"
                                        )
                            else:
                                # Clean up local file
                                try:
                                    Path(file_path).unlink()
                                    logger.info(f"Deleted local file: {file_path}")
                                except Exception as e:
                                    logger.warning(f"Failed to delete local file: {e}")

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
                    # Clean up temp file if it exists
                    if local_file_path and local_file_path.exists():
                        try:
                            local_file_path.unlink()
                        except:
                            pass

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
    if not filename or "." not in filename:
        logger.warning(f"Invalid filename format: {filename}")
        return False
    
    extension = filename.rsplit(".", 1)[1].lower()
    is_allowed = extension in ALLOWED_EXTENSIONS
    
    logger.info(f"File validation - filename: {filename}, extension: {extension}, allowed: {is_allowed}")
    return is_allowed

def clean_excel_file(file_path):
    """
    Clean Excel file by removing potentially problematic content like comments, drawings, etc.
    Returns the path to the cleaned file.
    """
    try:
        import pandas as pd
        import tempfile
        import os
        
        # Read the Excel file
        df = pd.read_excel(file_path)
        
        # Create a temporary cleaned file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.xlsx')
        os.close(temp_fd)
        
        # Save as a clean Excel file (removes comments, drawings, etc.)
        df.to_excel(temp_path, index=False)
        
        logger.info(f"Cleaned Excel file: {file_path} -> {temp_path}")
        return temp_path
        
    except Exception as e:
        logger.error(f"Failed to clean Excel file {file_path}: {str(e)}")
        return file_path  # Return original file if cleaning fails


@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
@app.route("/api/health", methods=["GET"])
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

        # Check storage status
        storage_status = {}
        if s3_manager:
            s3_check = s3_manager.check_bucket_access()
            storage_status = {
                "type": "s3",
                "s3_accessible": s3_check["accessible"],
                "bucket": s3_check["bucket"],
                "region": s3_check.get("region", config_manager.aws_region),
            }
            if not s3_check["accessible"]:
                storage_status["s3_error"] = s3_check.get("error", "Unknown")
        else:
            # Fallback to local storage check
            storage_status = {
                "type": "local",
                "upload_dir_exists": UPLOAD_FOLDER.exists(),
                "upload_dir_writable": UPLOAD_FOLDER.exists()
                and os.access(UPLOAD_FOLDER, os.W_OK),
                "upload_dir_path": str(UPLOAD_FOLDER),
            }

        return jsonify(
            {
                "status": "healthy",
                "service": "timecard-processor",
                "database": db_type,
                "queue_stats": stats,
                "storage": storage_status,
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


@app.route("/api/s3/test", methods=["GET", "OPTIONS"])
def test_s3_connection():
    """Test S3 connection and permissions"""
    try:
        if request.method == "OPTIONS":
            return "", 200

        if not s3_manager:
            return jsonify({"error": "S3 not configured"}), 500

        # Test bucket access
        access_check = s3_manager.check_bucket_access()
        
        # Test presigned URL generation
        test_result = s3_manager.generate_presigned_upload_url("test.txt")
        
        return jsonify({
            "s3_access": access_check,
            "presigned_url_test": {
                "success": test_result["success"],
                "error": test_result.get("error", None)
            }
        })

    except Exception as e:
        logger.error(f"S3 test failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/presigned-url", methods=["POST", "OPTIONS"])
def get_presigned_upload_url():
    """Get presigned URL for direct S3 upload"""
    try:
        logger.info(f"=== PRESIGNED URL REQUEST ===")
        logger.info(f"Method: {request.method}")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"S3 Manager available: {s3_manager is not None}")
        if s3_manager:
            logger.info(f"S3 Bucket: {s3_manager.bucket_name}")
            logger.info(f"S3 Region: {s3_manager.region}")
        
        if request.method == "OPTIONS":
            logger.info("Handling OPTIONS preflight request")
            return "", 200

        # Get request data
        try:
            data = request.get_json()
            logger.info(f"Request data: {data}")
        except Exception as json_e:
            logger.error(f"Failed to parse JSON: {json_e}")
            return jsonify({"error": "Invalid JSON in request body"}), 400

        if not data:
            logger.error("No data in request body")
            return jsonify({"error": "Request body is required"}), 400

        filename = data.get("filename")
        file_size = data.get("file_size", 0)

        logger.info(f"Filename: {filename}")
        logger.info(f"File size: {file_size}")

        if not filename:
            logger.error("No filename provided")
            return jsonify({"error": "Filename is required"}), 400

        # Validate file type
        if not allowed_file(filename):
            logger.error(f"Invalid file type: {filename}")
            return (
                jsonify({"error": "Invalid file type. Only Excel (.xlsx, .xls, .xlsm) and CSV files allowed"}),
                400,
            )

        # Validate file size
        if file_size <= 0:
            logger.error(f"Invalid file size: {file_size}")
            return jsonify({"error": "File size must be greater than 0"}), 400

        if file_size > 500 * 1024 * 1024:  # 500MB limit
            logger.error(f"File too large: {file_size} bytes")
            return jsonify({"error": "File size exceeds 500MB limit"}), 400

        # Check S3 manager
        if not s3_manager:
            logger.error("S3 manager not available for presigned URL generation")
            return (
                jsonify({"error": "S3 not configured. Please use regular upload."}),
                400,
            )

        # Use multipart upload for files larger than 100MB
        if file_size > 100 * 1024 * 1024:  # 100MB
            logger.info(
                f"Generating multipart upload URLs for large file: {filename} ({file_size} bytes)"
            )
            result = s3_manager.generate_multipart_upload_urls(filename, file_size)
        else:
            logger.info(
                f"Generating presigned upload URL for: {filename} ({file_size} bytes)"
            )
            result = s3_manager.generate_presigned_upload_url(filename)

        if result["success"]:
            return jsonify(
                {
                    "status": "success",
                    "upload_type": (
                        "multipart" if file_size > 100 * 1024 * 1024 else "single"
                    ),
                    **result,
                }
            )
        else:
            return (
                jsonify(
                    {
                        "error": "Failed to generate upload URL",
                        "details": result.get("error", "Unknown error"),
                    }
                ),
                500,
            )

    except Exception as e:
        logger.error(f"Failed to generate presigned upload URL: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/complete", methods=["POST", "OPTIONS"])
def complete_upload():
    """Complete upload and create processing job"""
    try:
        if request.method == "OPTIONS":
            return "", 200

        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        s3_key = data.get("s3_key")
        bucket = data.get("bucket")
        original_filename = data.get("original_filename")
        unique_filename = data.get("unique_filename")
        upload_timestamp = data.get("upload_timestamp")
        upload_type = data.get("upload_type", "single")

        if not all([s3_key, bucket, original_filename]):
            return jsonify({"error": "Missing required upload information"}), 400

        logger.info(f"Completing upload - s3_key: {s3_key}, bucket: {bucket}, filename: {original_filename}")

        # Verify S3 manager is available
        if not s3_manager:
            logger.error("S3 manager not available for upload completion")
            return jsonify({"error": "S3 not configured"}), 500

        # Verify file exists in S3
        try:
            s3_manager.s3_client.head_object(Bucket=bucket, Key=s3_key)
            logger.info(f"Confirmed S3 file exists: {s3_key}")
        except Exception as e:
            logger.error(f"S3 file verification failed: {e}")
            return jsonify({"error": f"Uploaded file not found in S3: {s3_key}"}), 400

        # For multipart uploads, complete the multipart upload first
        if upload_type == "multipart":
            upload_id = data.get("upload_id")
            parts = data.get("parts", [])

            if not upload_id or not parts:
                return jsonify({"error": "Missing multipart upload information"}), 400

            completion_result = s3_manager.complete_multipart_upload(
                s3_key, upload_id, parts
            )
            if not completion_result["success"]:
                return (
                    jsonify(
                        {
                            "error": "Failed to complete multipart upload",
                            "details": completion_result.get("error", "Unknown error"),
                        }
                    ),
                    500,
                )

            file_size = completion_result["file_size"]
        else:
            # For single uploads, get file size from S3
            try:
                response = s3_manager.s3_client.head_object(Bucket=bucket, Key=s3_key)
                file_size = response["ContentLength"]
            except Exception as e:
                logger.error(f"Failed to get file size from S3: {e}")
                return jsonify({"error": "Failed to verify uploaded file"}), 500

        # Create job with S3 information
        job_id = job_queue.create_job(
            job_type="timecard_processing",
            file_name=original_filename,
            file_size=file_size,
            priority=JobPriority.NORMAL,
            metadata={
                "storage_type": "s3",
                "s3_bucket": bucket,
                "s3_key": s3_key,
                "original_filename": original_filename,
                "unique_filename": unique_filename,
                "upload_timestamp": upload_timestamp,
                "upload_type": upload_type,
                "model_info": {
                    "model_id": config_manager.bedrock_model_id,
                    "aws_region": config_manager.aws_region,
                },
            },
        )

        logger.info(
            f"Job created for S3 upload: {job_id} - {original_filename} ({file_size} bytes)"
        )

        return jsonify(
            {
                "status": "success",
                "job_id": job_id,
                "message": "File uploaded and job created",
                "file_name": original_filename,
                "file_size": file_size,
            }
        )

    except Exception as e:
        logger.error(f"Failed to complete upload: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/abort", methods=["POST", "OPTIONS"])
def abort_upload():
    """Abort multipart upload"""
    try:
        if request.method == "OPTIONS":
            return "", 200

        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        s3_key = data.get("s3_key")
        upload_id = data.get("upload_id")

        if not all([s3_key, upload_id]):
            return jsonify({"error": "Missing required abort information"}), 400

        if not s3_manager:
            return jsonify({"error": "S3 not configured"}), 400

        success = s3_manager.abort_multipart_upload(s3_key, upload_id)

        if success:
            return jsonify({"status": "success", "message": "Upload aborted"})
        else:
            return jsonify({"error": "Failed to abort upload"}), 500

    except Exception as e:
        logger.error(f"Failed to abort upload: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload", methods=["POST", "OPTIONS"])
def upload_file():
    """Upload file and create processing job (fallback method)"""
    try:
        logger.info(f"=== UPLOAD REQUEST (FALLBACK) ===")
        logger.info(f"Method: {request.method}")
        logger.info(f"Path: {request.path}")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(
            f"Content-Length: {request.headers.get('Content-Length', 'Unknown')}"
        )
        logger.info(f"Files: {list(request.files.keys())}")

        if request.method == "OPTIONS":
            logger.info("Handling OPTIONS preflight request")
            return "", 200

        if "file" not in request.files:
            logger.warning("No file in request")
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            logger.warning("Empty filename")
            return jsonify({"error": "No file selected"}), 400

        if not allowed_file(file.filename):
            logger.warning(f"Invalid file type: {file.filename}")
            return (
                jsonify({"error": "Invalid file type. Only Excel (.xlsx, .xls, .xlsm) and CSV files allowed"}),
                400,
            )

        filename = secure_filename(file.filename)
        
        # Clean Excel files to remove potentially problematic content
        file_to_upload = file
        temp_file_path = None
        
        if filename.lower().endswith(('.xlsx', '.xls', '.xlsm')):
            logger.info(f"Cleaning Excel file: {filename}")
            try:
                # Save uploaded file temporarily
                import tempfile
                temp_fd, temp_upload_path = tempfile.mkstemp(suffix='.xlsx')
                with os.fdopen(temp_fd, 'wb') as tmp:
                    file.seek(0)
                    tmp.write(file.read())
                
                # Clean the file
                cleaned_path = clean_excel_file(temp_upload_path)
                
                if cleaned_path != temp_upload_path:
                    # File was cleaned, use the cleaned version
                    temp_file_path = cleaned_path
                    with open(cleaned_path, 'rb') as cleaned_file:
                        file_to_upload = cleaned_file
                        file_content = cleaned_file.read()
                        
                    # Create a file-like object from the cleaned content
                    from io import BytesIO
                    file_to_upload = BytesIO(file_content)
                    file_to_upload.filename = filename
                    
                    logger.info(f"Using cleaned version of {filename}")
                else:
                    # Cleaning failed, use original
                    file.seek(0)
                    
                # Clean up temp upload file
                os.unlink(temp_upload_path)
                
            except Exception as e:
                logger.error(f"Error cleaning Excel file: {str(e)}")
                file.seek(0)  # Use original file

        # Try S3 upload first, fallback to local storage
        if s3_manager:
            logger.info(f"Uploading file to S3: {filename}")

            # Reset file pointer to beginning
            file_to_upload.seek(0)

            upload_result = s3_manager.upload_file(file_to_upload, filename)

            if upload_result["success"]:
                logger.info(
                    f"File uploaded successfully to S3: {filename} ({upload_result['file_size']} bytes)"
                )

                # Create job with S3 information
                job_id = job_queue.create_job(
                    job_type="timecard_processing",
                    file_name=filename,
                    file_size=upload_result["file_size"],
                    priority=JobPriority.NORMAL,
                    metadata={
                        "storage_type": "s3",
                        "s3_bucket": upload_result["bucket"],
                        "s3_key": upload_result["s3_key"],
                        "original_filename": filename,
                        "unique_filename": upload_result["unique_filename"],
                        "upload_timestamp": upload_result["upload_timestamp"],
                        "model_info": {
                            "model_id": config_manager.bedrock_model_id,
                            "aws_region": config_manager.aws_region,
                        },
                    },
                )

                file_size = upload_result["file_size"]
            else:
                logger.error(
                    f"S3 upload failed: {upload_result.get('error', 'Unknown error')}"
                )
                return (
                    jsonify(
                        {
                            "error": "File upload failed",
                            "details": upload_result.get("error", "S3 upload error"),
                        }
                    ),
                    500,
                )
        else:
            # Fallback to local storage
            logger.info(f"S3 not available, using local storage: {filename}")

            # Check upload directory
            if not UPLOAD_FOLDER.exists():
                logger.error(f"Upload directory does not exist: {UPLOAD_FOLDER}")
                return jsonify({"error": "Upload directory not available"}), 500

            if not os.access(UPLOAD_FOLDER, os.W_OK):
                logger.error(f"Upload directory not writable: {UPLOAD_FOLDER}")
                return jsonify({"error": "Upload directory not writable"}), 500

            timestamp = int(time.time())
            unique_filename = f"{timestamp}_{filename}"
            file_path = UPLOAD_FOLDER / unique_filename

            logger.info(f"Saving file to: {file_path}")
            
            # Handle both regular file objects and BytesIO objects
            if hasattr(file_to_upload, 'save'):
                # Regular Flask file object
                file_to_upload.save(file_path)
            else:
                # BytesIO or other file-like object
                file_to_upload.seek(0)
                with open(file_path, 'wb') as f:
                    f.write(file_to_upload.read())

            # Get file size
            file_size = file_path.stat().st_size

            logger.info(
                f"File uploaded successfully to local storage: {filename} ({file_size} bytes)"
            )

            # Create job with local file information
            job_id = job_queue.create_job(
                job_type="timecard_processing",
                file_name=filename,
                file_size=file_size,
                priority=JobPriority.NORMAL,
                metadata={
                    "storage_type": "local",
                    "file_path": str(file_path),
                    "original_filename": filename,
                    "unique_filename": unique_filename,
                    "upload_timestamp": timestamp,
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
    finally:
        # Clean up temporary files
        if 'temp_file_path' in locals() and temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.info(f"Cleaned up temporary file: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {temp_file_path}: {e}")


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


@app.route("/api/automated-reasoning/cleanup", methods=["POST"])
def cleanup_automated_reasoning():
    """Clean up orphaned Automated Reasoning resources"""
    try:
        from automated_reasoning_provisioner import AutomatedReasoningProvisioner

        provisioner = AutomatedReasoningProvisioner(
            region_name=config_manager.aws_region, config_manager=config_manager
        )

        # Clean up orphaned resources
        result = provisioner.cleanup_orphaned_resources()

        return jsonify(
            {
                "status": "success",
                "message": "Cleanup completed",
                "result": result,
            }
        )

    except Exception as e:
        logger.error(f"Failed to cleanup Automated Reasoning resources: {e}")
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


@app.route("/api/debug/s3-status", methods=["GET"])
def debug_s3_status():
    """Debug endpoint to check S3 configuration and status"""
    try:
        status = {
            "s3_manager_initialized": s3_manager is not None,
            "s3_bucket_config": config_manager.s3_app_data_bucket,
            "aws_region": config_manager.aws_region,
        }
        
        if s3_manager:
            access_check = s3_manager.check_bucket_access()
            status.update({
                "bucket_accessible": access_check.get('accessible', False),
                "bucket_check_details": access_check
            })
            
            # Try to list a few objects
            try:
                objects = s3_manager.list_files(prefix="uploads/", max_keys=5)
                status["recent_uploads"] = [obj.get('Key', 'unknown') for obj in objects[:3]]
            except Exception as e:
                status["list_error"] = str(e)
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Debug S3 status failed: {e}")
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
