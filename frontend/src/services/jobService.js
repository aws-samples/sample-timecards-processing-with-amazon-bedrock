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
    const formData = new FormData();
    formData.append('file', file);

    const response = await axios.post(`${API_BASE}/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
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