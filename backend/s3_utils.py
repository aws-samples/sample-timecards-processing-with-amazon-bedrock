#!/usr/bin/env python3
"""
S3 utilities for file upload and management
"""

import boto3
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from botocore.exceptions import ClientError, NoCredentialsError
import time

logger = logging.getLogger(__name__)


class S3Manager:
    """Manages S3 operations for file uploads"""

    def __init__(self, bucket_name: str, region: str = "us-west-2"):
        self.bucket_name = bucket_name
        self.region = region

        try:
            self.s3_client = boto3.client("s3", region_name=region)
            logger.info(f"S3 client initialized for bucket: {bucket_name}")
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise

    def upload_file(
        self, file_obj, filename: str, folder: str = "uploads"
    ) -> Dict[str, Any]:
        """
        Upload file to S3 bucket

        Args:
            file_obj: File object to upload
            filename: Name of the file
            folder: S3 folder/prefix (default: "uploads")

        Returns:
            Dict with upload result information
        """
        try:
            # Generate unique filename with timestamp
            timestamp = int(time.time())
            unique_filename = f"{timestamp}_{filename}"
            s3_key = f"{folder}/{unique_filename}"

            # Upload file
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    "ServerSideEncryption": "AES256",
                    "Metadata": {
                        "original_filename": filename,
                        "upload_timestamp": str(timestamp),
                    },
                },
            )

            # Get file size
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            file_size = response["ContentLength"]

            logger.info(
                f"File uploaded successfully to S3: {s3_key} ({file_size} bytes)"
            )

            return {
                "success": True,
                "s3_key": s3_key,
                "bucket": self.bucket_name,
                "file_size": file_size,
                "unique_filename": unique_filename,
                "original_filename": filename,
                "upload_timestamp": timestamp,
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"S3 upload failed with error {error_code}: {e}")
            return {
                "success": False,
                "error": f"S3 upload failed: {error_code}",
                "details": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected error during S3 upload: {e}")
            return {
                "success": False,
                "error": "Unexpected upload error",
                "details": str(e),
            }

    def download_file(self, s3_key: str, local_path: str) -> bool:
        """
        Download file from S3 to local path

        Args:
            s3_key: S3 object key
            local_path: Local file path to save

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Attempting to download S3 file: s3://{self.bucket_name}/{s3_key} -> {local_path}")
            
            # Check if object exists first
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
                logger.info(f"S3 object exists: {s3_key}")
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.error(f"S3 object not found: {s3_key}")
                    return False
                else:
                    raise
            
            # Download the file
            self.s3_client.download_file(self.bucket_name, s3_key, local_path)
            
            # Verify download
            local_file = Path(local_path)
            if local_file.exists():
                file_size = local_file.stat().st_size
                logger.info(f"File downloaded successfully from S3: {s3_key} -> {local_path} ({file_size} bytes)")
                return True
            else:
                logger.error(f"Downloaded file does not exist: {local_path}")
                return False
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 download failed with error {error_code}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during S3 download: {e}")
            return False

    def get_file_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate presigned URL for S3 object

        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL or None if failed
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return None

    def generate_presigned_upload_url(
        self, filename: str, folder: str = "uploads", expiration: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate presigned URL for direct S3 upload

        Args:
            filename: Original filename
            folder: S3 folder/prefix (default: "uploads")
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Dict with presigned URL and upload information
        """
        try:
            # Generate unique filename with timestamp
            timestamp = int(time.time())
            unique_filename = f"{timestamp}_{filename}"
            s3_key = f"{folder}/{unique_filename}"

            # Generate presigned PUT URL for upload (simpler and more reliable)
            logger.info(f"Attempting to generate PUT presigned URL for: {s3_key}")
            
            upload_url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key,
                    'ContentType': 'application/octet-stream'
                },
                ExpiresIn=expiration
            )

            logger.info(f"Successfully generated presigned PUT URL for: {s3_key}")
            logger.info(f"PUT URL: {upload_url}")

            return {
                "success": True,
                "upload_url": upload_url,
                "method": "PUT",
                "s3_key": s3_key,
                "bucket": self.bucket_name,
                "unique_filename": unique_filename,
                "original_filename": filename,
                "upload_timestamp": timestamp,
                "expires_in": expiration,
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"Failed to generate presigned upload URL: {error_code} - {e}")
            return {
                "success": False,
                "error": f"Failed to generate upload URL: {error_code}",
                "details": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected error generating presigned upload URL: {e}")
            return {
                "success": False,
                "error": "Unexpected error generating upload URL",
                "details": str(e),
            }

    def generate_multipart_upload_urls(
        self, filename: str, file_size: int, folder: str = "uploads", 
        chunk_size: int = 10 * 1024 * 1024, expiration: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate presigned URLs for multipart upload (for files > 100MB)

        Args:
            filename: Original filename
            file_size: Total file size in bytes
            folder: S3 folder/prefix (default: "uploads")
            chunk_size: Size of each part in bytes (default: 10MB)
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Dict with multipart upload information and presigned URLs
        """
        try:
            # Generate unique filename with timestamp
            timestamp = int(time.time())
            unique_filename = f"{timestamp}_{filename}"
            s3_key = f"{folder}/{unique_filename}"

            # Calculate number of parts
            num_parts = (file_size + chunk_size - 1) // chunk_size

            # Initiate multipart upload
            response = self.s3_client.create_multipart_upload(
                Bucket=self.bucket_name,
                Key=s3_key,
                ServerSideEncryption="AES256",
                Metadata={
                    "original_filename": filename,
                    "upload_timestamp": str(timestamp),
                },
            )

            upload_id = response["UploadId"]

            # Generate presigned URLs for each part
            part_urls = []
            for part_number in range(1, num_parts + 1):
                part_url = self.s3_client.generate_presigned_url(
                    "upload_part",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": s3_key,
                        "PartNumber": part_number,
                        "UploadId": upload_id,
                    },
                    ExpiresIn=expiration,
                )
                part_urls.append({
                    "part_number": part_number,
                    "upload_url": part_url,
                })

            logger.info(f"Generated multipart upload URLs for: {s3_key} ({num_parts} parts)")

            return {
                "success": True,
                "upload_id": upload_id,
                "s3_key": s3_key,
                "bucket": self.bucket_name,
                "unique_filename": unique_filename,
                "original_filename": filename,
                "upload_timestamp": timestamp,
                "num_parts": num_parts,
                "chunk_size": chunk_size,
                "part_urls": part_urls,
                "expires_in": expiration,
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"Failed to generate multipart upload URLs: {error_code} - {e}")
            return {
                "success": False,
                "error": f"Failed to generate multipart upload URLs: {error_code}",
                "details": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected error generating multipart upload URLs: {e}")
            return {
                "success": False,
                "error": "Unexpected error generating multipart upload URLs",
                "details": str(e),
            }

    def complete_multipart_upload(
        self, s3_key: str, upload_id: str, parts: list
    ) -> Dict[str, Any]:
        """
        Complete multipart upload

        Args:
            s3_key: S3 object key
            upload_id: Multipart upload ID
            parts: List of completed parts with ETag and PartNumber

        Returns:
            Dict with completion result
        """
        try:
            response = self.s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            # Get file size
            head_response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            file_size = head_response["ContentLength"]

            logger.info(f"Multipart upload completed: {s3_key} ({file_size} bytes)")

            return {
                "success": True,
                "s3_key": s3_key,
                "bucket": self.bucket_name,
                "file_size": file_size,
                "etag": response["ETag"],
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"Failed to complete multipart upload: {error_code} - {e}")
            return {
                "success": False,
                "error": f"Failed to complete multipart upload: {error_code}",
                "details": str(e),
            }
        except Exception as e:
            logger.error(f"Unexpected error completing multipart upload: {e}")
            return {
                "success": False,
                "error": "Unexpected error completing multipart upload",
                "details": str(e),
            }

    def abort_multipart_upload(self, s3_key: str, upload_id: str) -> bool:
        """
        Abort multipart upload

        Args:
            s3_key: S3 object key
            upload_id: Multipart upload ID

        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.abort_multipart_upload(
                Bucket=self.bucket_name, Key=s3_key, UploadId=upload_id
            )
            logger.info(f"Multipart upload aborted: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to abort multipart upload: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error aborting multipart upload: {e}")
            return False

    def delete_file(self, s3_key: str) -> bool:
        """
        Delete file from S3

        Args:
            s3_key: S3 object key to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"File deleted from S3: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"S3 delete failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during S3 delete: {e}")
            return False

    def list_files(self, prefix: str = "uploads/", max_keys: int = 100) -> list:
        """
        List files in S3 bucket with given prefix

        Args:
            prefix: S3 key prefix to filter
            max_keys: Maximum number of keys to return

        Returns:
            List of S3 objects
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys
            )

            if "Contents" in response:
                return response["Contents"]
            else:
                return []

        except ClientError as e:
            logger.error(f"S3 list failed: {e}")
            return []

    def check_bucket_access(self) -> Dict[str, Any]:
        """
        Check if bucket exists and is accessible

        Returns:
            Dict with access check results
        """
        try:
            # Try to list objects (this checks both existence and permissions)
            self.s3_client.head_bucket(Bucket=self.bucket_name)

            # Try a simple list operation
            self.s3_client.list_objects_v2(Bucket=self.bucket_name, MaxKeys=1)

            return {
                "accessible": True,
                "bucket": self.bucket_name,
                "region": self.region,
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            return {
                "accessible": False,
                "bucket": self.bucket_name,
                "error": error_code,
                "message": str(e),
            }
        except Exception as e:
            return {
                "accessible": False,
                "bucket": self.bucket_name,
                "error": "UnknownError",
                "message": str(e),
            }
