import axios from 'axios';

const API_BASE = process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:8000/api';

// Add response interceptor to handle errors consistently
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    // Enhance error with more details
    if (error.response?.data) {
      const errorData = error.response.data;
      error.message = `${errorData.error || error.message}${errorData.function ? ` (${errorData.function})` : ''}${errorData.endpoint ? ` [${errorData.endpoint}]` : ''}`;
    }
    return Promise.reject(error);
  }
);

class JobService {
  async uploadFile(file, onProgress) {
    try {
      // Try presigned URL upload first (for S3)
      return await this.uploadFileWithPresignedUrl(file, onProgress);
    } catch (error) {
      console.warn('Presigned URL upload failed, falling back to direct upload:', error.message);
      // Fallback to direct upload through backend
      return await this.uploadFileDirectly(file, onProgress);
    }
  }

  async uploadFileWithPresignedUrl(file, onProgress) {
    try {
      // Step 1: Get presigned URL
      console.log('Requesting presigned URL for:', {
        filename: file.name,
        file_size: file.size,
        file_type: file.type
      });

      const presignedResponse = await axios.post(`${API_BASE}/upload/presigned-url`, {
        filename: file.name,
        file_size: file.size
      }, {
        headers: {
          'Content-Type': 'application/json',
        }
      });

      console.log('Presigned URL response:', presignedResponse.data);

      const { upload_type, ...uploadInfo } = presignedResponse.data;
      
      console.log('Upload method:', uploadInfo.method);
      console.log('Upload URL:', uploadInfo.upload_url);
      console.log('Has fields (POST):', !!uploadInfo.fields);
      console.log('Full uploadInfo:', uploadInfo);

      if (upload_type === 'multipart') {
        return await this.uploadFileMultipart(file, uploadInfo, onProgress);
      } else {
        return await this.uploadFileSingle(file, uploadInfo, onProgress);
      }
    } catch (error) {
      console.error('Presigned URL request failed:', {
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        message: error.message
      });
      throw error;
    }
  }

  async uploadFileSingle(file, uploadInfo, onProgress) {
    // Step 2: Upload directly to S3 using presigned URL
    console.log('uploadFileSingle - method:', uploadInfo.method);
    console.log('uploadFileSingle - uploadInfo:', uploadInfo);
    
    if (uploadInfo.method === 'PUT') {
      console.log('Using PUT method for upload');
      // Use PUT method for simple presigned URL
      await axios.put(uploadInfo.upload_url, file, {
        headers: {
          'Content-Type': 'application/octet-stream',
        },
        timeout: 300000, // 5 minute timeout
        onUploadProgress: (progressEvent) => {
          if (onProgress) {
            const percentCompleted = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            onProgress(percentCompleted);
          }
        },
      });
    } else {
      // Use POST method with form data
      console.log('Using POST method for upload');
      const formData = new FormData();
      
      // Add all the fields from presigned URL
      if (uploadInfo.fields) {
        Object.keys(uploadInfo.fields).forEach(key => {
          formData.append(key, uploadInfo.fields[key]);
        });
      }
      
      // Add the file last
      formData.append('file', file);

      await axios.post(uploadInfo.upload_url, formData, {
        headers: {
          // Don't set Content-Type, let browser set it with boundary
        },
        timeout: 300000, // 5 minute timeout
        onUploadProgress: (progressEvent) => {
          if (onProgress) {
            const percentCompleted = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            onProgress(percentCompleted);
          }
        },
      });
    }

    // Step 3: Complete the upload and create job
    const completeResponse = await axios.post(`${API_BASE}/upload/complete`, {
      s3_key: uploadInfo.s3_key,
      bucket: uploadInfo.bucket,
      original_filename: uploadInfo.original_filename,
      unique_filename: uploadInfo.unique_filename,
      upload_timestamp: uploadInfo.upload_timestamp,
      upload_type: 'single'
    });

    return completeResponse.data;
  }

  async uploadFileMultipart(file, uploadInfo, onProgress) {
    const { part_urls, upload_id, chunk_size } = uploadInfo;
    const parts = [];
    let uploadedBytes = 0;

    try {
      // Upload each part
      for (let i = 0; i < part_urls.length; i++) {
        const partInfo = part_urls[i];
        const start = (partInfo.part_number - 1) * chunk_size;
        const end = Math.min(start + chunk_size, file.size);
        const chunk = file.slice(start, end);
        const currentUploadedBytes = uploadedBytes; // Capture current value

        const response = await axios.put(partInfo.upload_url, chunk, {
          headers: {
            'Content-Type': 'application/octet-stream',
          },
          timeout: 300000, // 5 minute timeout per part
          onUploadProgress: (progressEvent) => {
            if (onProgress) {
              const partProgress = (currentUploadedBytes + progressEvent.loaded) / file.size * 100;
              onProgress(Math.round(partProgress));
            }
          },
        });

        parts.push({
          ETag: response.headers.etag,
          PartNumber: partInfo.part_number
        });

        uploadedBytes += chunk.size;
        
        if (onProgress) {
          onProgress(Math.round((uploadedBytes / file.size) * 100));
        }
      }

      // Complete the multipart upload and create job
      const completeResponse = await axios.post(`${API_BASE}/upload/complete`, {
        s3_key: uploadInfo.s3_key,
        bucket: uploadInfo.bucket,
        original_filename: uploadInfo.original_filename,
        unique_filename: uploadInfo.unique_filename,
        upload_timestamp: uploadInfo.upload_timestamp,
        upload_type: 'multipart',
        upload_id: upload_id,
        parts: parts
      });

      return completeResponse.data;

    } catch (error) {
      // Abort the multipart upload on error
      try {
        await axios.post(`${API_BASE}/upload/abort`, {
          s3_key: uploadInfo.s3_key,
          upload_id: upload_id
        });
      } catch (abortError) {
        console.error('Failed to abort multipart upload:', abortError);
      }
      throw error;
    }
  }

  async uploadFileDirectly(file, onProgress) {
    // Fallback: Direct upload through backend (original method)
    const formData = new FormData();
    formData.append('file', file);

    const response = await axios.post(`${API_BASE}/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 300000, // 5 minute timeout for large file uploads
      maxContentLength: 500 * 1024 * 1024, // 500MB max content length
      maxBodyLength: 500 * 1024 * 1024, // 500MB max body length
      onUploadProgress: (progressEvent) => {
        if (onProgress) {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          onProgress(percentCompleted);
        }
      },
    });

    return response.data;
  }

  async getJobs(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.status && params.status.length > 0) {
      params.status.forEach(status => queryParams.append('status', status));
    }

    const response = await axios.get(`${API_BASE}/jobs?${queryParams}`);
    return response.data;
  }

  async getJob(jobId) {
    const response = await axios.get(`${API_BASE}/jobs/${jobId}`);
    return response.data;
  }

  async cancelJob(jobId) {
    const response = await axios.post(`${API_BASE}/jobs/${jobId}/cancel`);
    return response.data;
  }

  async stopJob(jobId) {
    const response = await axios.post(`${API_BASE}/jobs/${jobId}/stop`);
    return response.data;
  }

  async deleteJob(jobId) {
    const response = await axios.delete(`${API_BASE}/jobs/${jobId}`);
    return response.data;
  }

  async bulkDeleteJobs(jobIds) {
    const response = await axios.post(`${API_BASE}/jobs/bulk-delete`, { job_ids: jobIds });
    return response.data;
  }

  async getQueueStats() {
    const response = await axios.get(`${API_BASE}/queue/stats`);
    return response.data;
  }

  async getReviewQueue() {
    const response = await axios.get(`${API_BASE}/review-queue`);
    return response.data;
  }

  async completeReview(jobId) {
    const response = await axios.post(`${API_BASE}/jobs/${jobId}/complete-review`);
    return response.data;
  }

  async bulkCompleteReview(jobIds) {
    const response = await axios.post(`${API_BASE}/jobs/bulk-complete-review`, { job_ids: jobIds });
    return response.data;
  }

  async cleanupQueue(days = 7) {
    const response = await axios.post(`${API_BASE}/queue/cleanup`, { days });
    return response.data;
  }

  async getSamples() {
    const response = await axios.get(`${API_BASE}/samples`);
    return response.data;
  }

  async processSample(filename) {
    const response = await axios.get(`${API_BASE}/process-sample/${filename}`);
    return response.data;
  }

  async getSettings() {
    const response = await axios.get(`${API_BASE}/settings`);
    return response.data;
  }

  async updateSettings(settings) {
    const response = await axios.post(`${API_BASE}/settings`, settings);
    return response.data;
  }

  async getSetting(key) {
    const response = await axios.get(`${API_BASE}/settings/${key}`);
    return response.data;
  }

  async updateSetting(key, value) {
    const response = await axios.put(`${API_BASE}/settings/${key}`, { value });
    return response.data;
  }

  // Utility methods
  formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  formatDuration(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${Math.round(seconds / 3600)}h`;
  }

  getStatusColor(status) {
    const colors = {
      pending: 'blue',
      processing: 'in-progress',
      completed: 'success',
      failed: 'error',
      cancelled: 'stopped'
    };
    return colors[status] || 'grey';
  }

  getPriorityColor(priority) {
    const colors = {
      1: 'grey',    // LOW
      2: 'blue',    // NORMAL
      3: 'orange',  // HIGH
      4: 'red'      // URGENT
    };
    return colors[priority] || 'grey';
  }

  getPriorityText(priority) {
    const texts = {
      1: 'Low',
      2: 'Normal',
      3: 'High',
      4: 'Urgent'
    };
    return texts[priority] || 'Normal';
  }

  async downloadJobFile(jobId, fileName) {
    try {
      const response = await axios.get(`${API_BASE}/jobs/${jobId}/download`, {
        responseType: 'blob'
      });

      // Create blob link to download
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      
      // Use the original filename or fallback
      link.setAttribute('download', fileName || `job_${jobId}_file`);
      document.body.appendChild(link);
      link.click();
      
      // Cleanup
      link.remove();
      window.URL.revokeObjectURL(url);
      
      return true;
    } catch (error) {
      console.error('Download failed:', error);
      throw error;
    }
  }
}

export const jobService = new JobService();