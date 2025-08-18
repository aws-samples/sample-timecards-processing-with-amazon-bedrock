import React, { useState, useEffect, useCallback } from 'react';
import {
  Header,
  SpaceBetween,
  Container,
  ColumnLayout,
  Box,
  StatusIndicator,
  ProgressBar,
  Button,
  Cards,
  Badge,
  Link,
  Alert
} from '@cloudscape-design/components';
import { jobService } from '../services/jobService';

const Dashboard = ({ addNotification }) => {
  const [stats, setStats] = useState({});
  const [recentJobs, setRecentJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [errorCount, setErrorCount] = useState(0);
  const [hasError, setHasError] = useState(false);

  const fetchDashboardData = useCallback(async () => {
    // Skip if we've had too many errors
    if (errorCount >= 5) {
      setHasError(true);
      return;
    }

    try {
      // Fetch stats and jobs first (these should work)
      const [statsData, jobsData] = await Promise.all([
        jobService.getQueueStats(),
        jobService.getJobs({ limit: 10 })
      ]);

      setStats(statsData);
      setRecentJobs(jobsData.jobs || []);

      // Try to fetch review queue separately to avoid breaking the whole dashboard
      try {
        const reviewData = await jobService.getReviewQueue();
        setReviewQueue(reviewData.review_queue || []);
      } catch (reviewError) {
        console.error('Review queue error:', reviewError);
        
        // Show specific error notification for review queue
        addNotification({
          type: 'error',
          header: 'Review Queue Error',
          content: `Failed to load review queue: ${reviewError.response?.data?.error || reviewError.message}. Function: ${reviewError.response?.data?.function || 'unknown'}`
        });
        
        setReviewQueue([]); // Set empty array instead of failing
      }

      setLoading(false);
      setErrorCount(0); // Reset error count on success
      setHasError(false);
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
      const newErrorCount = errorCount + 1;
      setErrorCount(newErrorCount);
      
      // Show detailed error information
      const errorDetails = error.response?.data || {};
      const errorMessage = errorDetails.error || error.message;
      const functionName = errorDetails.function || 'unknown';
      const endpoint = errorDetails.endpoint || 'unknown';
      
      // Only show notification for first error to avoid spam
      if (errorCount === 0) {
        addNotification({
          type: 'error',
          header: 'Dashboard Error',
          content: `${errorMessage} (Function: ${functionName}, Endpoint: ${endpoint})`
        });
      }
      
      // Stop polling after 5 errors
      if (newErrorCount >= 5) {
        setHasError(true);
      }
      
      setLoading(false);
    }
  }, [addNotification, errorCount]);

  useEffect(() => {
    fetchDashboardData();
    
    // Only set up polling if we don't have persistent errors
    if (!hasError) {
      const interval = setInterval(() => {
        if (errorCount < 5) {
          fetchDashboardData();
        }
      }, 15000); // Refresh every 15 seconds (reduced frequency)
      return () => clearInterval(interval);
    }
  }, [fetchDashboardData, hasError, errorCount]);



  const formatTime = (dateString) => {
    if (!dateString) return 'N/A';

    const date = new Date(dateString);
    // Use user's local timezone with detailed formatting
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZoneName: 'short'
    });
  };



  if (hasError) {
    return (
      <SpaceBetween size="l">
        <Header variant="h1">Timecard Processing Dashboard</Header>
        <Alert
          type="error"
          header="Dashboard Service Unavailable"
          action={
            <Button
              onClick={() => {
                setErrorCount(0);
                setHasError(false);
                fetchDashboardData();
              }}
            >
              Retry
            </Button>
          }
        >
          The dashboard service is temporarily unavailable. This may be due to database connectivity issues.
        </Alert>
      </SpaceBetween>
    );
  }

  return (
    <SpaceBetween size="l">
      <Header
        variant="h1"
        description="Monitor timecard processing jobs and system performance"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button onClick={fetchDashboardData} loading={loading}>
              Refresh
            </Button>
            <Button variant="primary" href="/upload">
              Upload Files
            </Button>
          </SpaceBetween>
        }
      >
        Timecard Processing Dashboard
      </Header>

      {/* Key Metrics */}
      <Container>
        <ColumnLayout columns={6} variant="text-grid">
          <div>
            <Box variant="awsui-key-label">Total Jobs</Box>
            <Box variant="awsui-value-large">{stats.total_jobs || 0}</Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Processing</Box>
            <Box variant="awsui-value-large" color={(stats.processing || 0) > 0 ? "text-status-info" : undefined}>
              {stats.processing || 0}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Completed</Box>
            <Box variant="awsui-value-large" color="text-status-success">
              {stats.completed || 0}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Failed</Box>
            <Box variant="awsui-value-large" color={(stats.failed || 0) > 0 ? "text-status-error" : undefined}>
              {stats.failed || 0}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Review Queue</Box>
            <Box variant="awsui-value-large" color={(stats.review_queue || 0) > 0 ? "text-status-warning" : undefined}>
              {stats.review_queue || 0}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Avg Processing Time</Box>
            <Box variant="awsui-value-large">
              {stats.avg_processing_time ? `${stats.avg_processing_time}s` : '0s'}
            </Box>
          </div>
        </ColumnLayout>
      </Container>

      {/* Additional Metrics */}
      <Container
        header={
          <Header variant="h2">
            Performance Metrics
          </Header>
        }
      >
        <ColumnLayout columns={4} variant="text-grid">
          <div>
            <Box variant="awsui-key-label">Success Rate</Box>
            <Box variant="awsui-value-large" color="text-status-success">
              {stats.success_rate ? `${stats.success_rate.toFixed(1)}%` : '0%'}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Jobs Today</Box>
            <Box variant="awsui-value-large">{stats.jobs_today || 0}</Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Pending</Box>
            <Box variant="awsui-value-large" color={(stats.pending || 0) > 0 ? "text-status-info" : undefined}>
              {stats.pending || 0}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Cancelled</Box>
            <Box variant="awsui-value-large">{stats.cancelled || 0}</Box>
          </div>
        </ColumnLayout>
      </Container>



      {/* Review Queue */}
      {reviewQueue.length > 0 && (
        <Container
          header={
            <Header
              variant="h2"
              counter={`(${reviewQueue.length})`}
              description="Jobs requiring human review"
            >
              Review Queue
            </Header>
          }
        >
          <Cards
            cardDefinition={{
              header: item => (
                <Link href={`/jobs/${item.job_id}`} fontSize="heading-s">
                  {item.file_name || 'Unknown File'} - {item.employee_name}
                </Link>
              ),
              sections: [
                {
                  id: "status",
                  content: item => (
                    <StatusIndicator type="warning">
                      Requires Review
                    </StatusIndicator>
                  )
                },
                {
                  id: "details",
                  content: item => (
                    <ColumnLayout columns={3} variant="text-grid">
                      <div>
                        <Box variant="awsui-key-label">Unique Days</Box>
                        <Box>{item.unique_days || item.total_days || 0}</Box>
                      </div>
                      <div>
                        <Box variant="awsui-key-label">Daily Rate</Box>
                        <Box>${(item.average_daily_rate || 0).toFixed(2)}</Box>
                      </div>
                      <div>
                        <Box variant="awsui-key-label">Total Wage</Box>
                        <Box>${(item.total_wage || 0).toFixed(2)}</Box>
                      </div>
                    </ColumnLayout>
                  )
                },
                {
                  id: "issues",
                  content: item => (
                    <SpaceBetween size="s">
                      <div>
                        <Box variant="awsui-key-label">Issues ({(item.validation_issues || []).length})</Box>
                        <SpaceBetween size="xs">
                          {(item.validation_issues || []).slice(0, 2).map((issue, index) => (
                            <Box key={index} variant="small" color="text-status-warning">
                              • {issue}
                            </Box>
                          ))}
                          {(item.validation_issues || []).length > 2 && (
                            <Box variant="small" color="text-body-secondary">
                              +{(item.validation_issues || []).length - 2} more issues
                            </Box>
                          )}
                        </SpaceBetween>
                      </div>
                      <div>
                        <Box variant="awsui-key-label">Created</Box>
                        <Box variant="small">{formatTime(item.created_at)}</Box>
                      </div>
                    </SpaceBetween>
                  )
                }
              ]
            }}
            cardsPerRow={[
              { cards: 1 },
              { minWidth: 500, cards: 2 },
              { minWidth: 800, cards: 3 }
            ]}
            items={reviewQueue}
            empty={
              <Box textAlign="center" color="inherit">
                <b>No items in review queue</b>
                <Box variant="p" color="inherit">
                  All processed timecards are compliant.
                </Box>
              </Box>
            }
          />
        </Container>
      )}

      {/* Recent Jobs */}
      <Container
        header={
          <Header
            variant="h2"
            actions={
              <Button href="/jobs">View All Jobs</Button>
            }
          >
            Recent Jobs
          </Header>
        }
      >
        <Cards
          cardDefinition={{
            header: item => (
              <Link href={`/jobs/${item.id}`} fontSize="heading-s">
                {item.file_name || 'Unknown File'}
              </Link>
            ),
            sections: [
              {
                id: "status",
                content: item => (
                  <SpaceBetween direction="horizontal" size="xs">
                    <StatusIndicator type={jobService.getStatusColor(item.status)}>
                      {item.status ? item.status.charAt(0).toUpperCase() + item.status.slice(1) : 'Unknown'}
                    </StatusIndicator>
                    <Badge color={jobService.getPriorityColor(item.priority)}>
                      {jobService.getPriorityText(item.priority)}
                    </Badge>
                  </SpaceBetween>
                )
              },
              {
                id: "progress",
                content: item => item.status === 'processing' ? (
                  <ProgressBar
                    value={item.progress || 0}
                    label="Progress"
                    description={`${item.progress || 0}% complete`}
                  />
                ) : null
              },
              {
                id: "details",
                content: item => (
                  <ColumnLayout columns={2} variant="text-grid">
                    <div>
                      <Box variant="awsui-key-label">Created</Box>
                      <Box>{formatTime(item.created_at)}</Box>
                    </div>
                    <div>
                      <Box variant="awsui-key-label">Size</Box>
                      <Box>{jobService.formatFileSize(item.file_size || 0)}</Box>
                    </div>
                  </ColumnLayout>
                )
              }
            ]
          }}
          cardsPerRow={[
            { cards: 1 },
            { minWidth: 500, cards: 2 },
            { minWidth: 800, cards: 3 }
          ]}
          items={recentJobs}
          loading={loading}
          empty={
            <Box textAlign="center" color="inherit">
              <b>No jobs found</b>
              <Box variant="p" color="inherit">
                Upload a timecard file to get started.
              </Box>
            </Box>
          }
        />
      </Container>

      {/* System Health */}
      <Container
        header={
          <Header variant="h2">
            System Health
          </Header>
        }
      >
        <ColumnLayout columns={3} variant="text-grid">
          <div>
            <Box variant="awsui-key-label">Queue Status</Box>
            <StatusIndicator type={stats.pending > 100 ? "warning" : "success"}>
              {stats.pending > 100 ? "High Load" : "Normal"}
            </StatusIndicator>
          </div>
          <div>
            <Box variant="awsui-key-label">Processing Capacity</Box>
            <StatusIndicator type={stats.processing > 5 ? "warning" : "success"}>
              {stats.processing > 5 ? "Near Capacity" : "Available"}
            </StatusIndicator>
          </div>
          <div>
            <Box variant="awsui-key-label">Review Queue Status</Box>
            <StatusIndicator type={reviewQueue.length > 0 ? "warning" : "success"}>
              {reviewQueue.length > 0 ? `${reviewQueue.length} Pending` : "Clear"}
            </StatusIndicator>
          </div>
        </ColumnLayout>
      </Container>
    </SpaceBetween>
  );
};

export default Dashboard;