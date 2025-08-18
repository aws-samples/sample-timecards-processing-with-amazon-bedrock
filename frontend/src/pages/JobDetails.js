import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Header,
  SpaceBetween,
  Container,
  ColumnLayout,
  Box,
  StatusIndicator,
  Button,
  ProgressBar,
  Table,
  Tabs,
  Alert,
  Modal,
  KeyValuePairs,
  Pagination,
  CollectionPreferences
} from '@cloudscape-design/components';
import { CodeView } from "@cloudscape-design/code-view";
import jsonHighlight from "@cloudscape-design/code-view/highlight/json";
import { jobService } from '../services/jobService';

// Import markdown components
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const JobDetails = ({ addNotification }) => {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const intervalRef = useRef(null);
  
  // Timecard pagination state
  const [timecardPageIndex, setTimecardPageIndex] = useState(1);
  const [timecardPreferences, setTimecardPreferences] = useState({
    pageSize: 25,
    visibleContent: ['employee', 'date', 'rate', 'project', 'department']
  });
  const [completingReview, setCompletingReview] = useState(false);
  const [showStopModal, setShowStopModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const fetchJob = useCallback(async () => {
    try {
      setError(null);
      const jobData = await jobService.getJob(jobId);
      setJob(jobData);
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch job:', error);

      // If job not found (404), set job to null
      if (error.response?.status === 404) {
        setJob(null);
        setLoading(false);
        return;
      }

      // For other errors, set error state
      setError({
        type: 'network',
        message: error.response?.data?.error || error.message,
        status: error.response?.status
      });
      setLoading(false);
    }
  }, [jobId]);

  // Start polling function
  const startPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }

    intervalRef.current = setInterval(() => {
      fetchJob();
    }, 3000);
  }, [fetchJob]);

  // Stop polling function
  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    fetchJob();
    return () => stopPolling();
  }, [fetchJob, stopPolling]);

  // Handle polling based on job status
  useEffect(() => {
    if (job?.status) {
      if (['pending', 'processing'].includes(job.status)) {
        startPolling();
      } else {
        stopPolling();
      }
    }

    return () => stopPolling();
  }, [job?.status, startPolling, stopPolling]);

  const handleCancelJob = async () => {
    try {
      await jobService.cancelJob(jobId);
      addNotification({
        type: 'success',
        header: 'Job cancelled',
        content: `Job has been cancelled successfully`
      });
      fetchJob();
    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Failed to cancel job',
        content: error.message
      });
    } finally {
      setShowCancelModal(false);
    }
  };

  const handleCompleteReview = async () => {
    try {
      setCompletingReview(true);
      await jobService.completeReview(jobId);
      addNotification({
        type: 'success',
        header: 'Review completed',
        content: 'The review has been marked as completed'
      });
      fetchJob();
    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Failed to complete review',
        content: error.message
      });
    } finally {
      setCompletingReview(false);
    }
  };

  const handleStopJob = async () => {
    try {
      await jobService.stopJob(jobId);
      addNotification({
        type: 'success',
        header: 'Job stopped',
        content: 'The job has been stopped'
      });
      fetchJob();
    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Failed to stop job',
        content: error.message
      });
    } finally {
      setShowStopModal(false);
    }
  };

  const handleDeleteJob = async () => {
    try {
      await jobService.deleteJob(jobId);
      addNotification({
        type: 'success',
        header: 'Job deleted',
        content: 'The job has been deleted'
      });
      navigate('/jobs');
    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Failed to delete job',
        content: error.message
      });
    } finally {
      setShowDeleteModal(false);
    }
  };

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

  const calculateDuration = (createdAt, completedAt) => {
    if (!createdAt || !completedAt) return 'N/A';

    const startTime = new Date(createdAt);
    const endTime = new Date(completedAt);
    const durationMs = endTime - startTime;

    if (durationMs < 0) return 'N/A';

    // Handle very short durations more gracefully
    if (durationMs < 1000) {
      return `${durationMs}ms`;
    }

    const seconds = Math.floor(durationMs / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) return `${days}d ${hours % 24}h ${minutes % 60}m`;
    if (hours > 0) return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    if (seconds > 0) return `${seconds}s`;
    return `${durationMs}ms`;
  };

  const renderTimecardData = () => {
    if (!job?.result?.extracted_data?.daily_entries) return null;

    const entries = job.result.extracted_data.daily_entries;
    const columnDefinitions = [
      {
        id: 'employee',
        header: 'Employee',
        cell: item => item[0] || 'N/A'
      },
      {
        id: 'date',
        header: 'Date',
        cell: item => item[1] || 'N/A'
      },
      {
        id: 'rate',
        header: 'Daily Rate',
        cell: item => `$${(item[2] || 0).toFixed(2)}`
      },
      {
        id: 'project',
        header: 'Project',
        cell: item => item[3] || 'N/A'
      },
      {
        id: 'department',
        header: 'Department',
        cell: item => item[4] || 'N/A'
      }
    ];

    // Transform entries for sorting and pagination
    const transformedEntries = entries.map((entry, index) => ({
      id: index,
      employee: entry[0] || 'N/A',
      date: entry[1] || 'N/A',
      rate: entry[2] || 0,
      project: entry[3] || 'N/A',
      department: entry[4] || 'N/A',
      originalEntry: entry
    }));

    // Update column definitions for sorting
    const updatedColumnDefinitions = [
      {
        id: 'employee',
        header: 'Employee',
        cell: item => item.employee,
        sortingField: 'employee'
      },
      {
        id: 'date',
        header: 'Date',
        cell: item => item.date,
        sortingField: 'date'
      },
      {
        id: 'rate',
        header: 'Daily Rate',
        cell: item => `$${(item.rate || 0).toFixed(2)}`,
        sortingField: 'rate'
      },
      {
        id: 'project',
        header: 'Project',
        cell: item => item.project,
        sortingField: 'project'
      },
      {
        id: 'department',
        header: 'Department',
        cell: item => item.department,
        sortingField: 'department'
      }
    ];

    // Get paginated items
    const getPaginatedItems = () => {
      const startIndex = (timecardPageIndex - 1) * timecardPreferences.pageSize;
      const endIndex = startIndex + timecardPreferences.pageSize;
      return transformedEntries.slice(startIndex, endIndex);
    };

    return (
      <Table
        columnDefinitions={updatedColumnDefinitions.map(col => ({
          ...col,
          cell: col.id === 'rate' ? 
            (item => `$${(item.rate || 0).toFixed(2)}`) : 
            col.cell
        }))}
        items={getPaginatedItems()}
        sortingDisabled={false}
        pagination={
          <Pagination
            currentPageIndex={timecardPageIndex}
            onChange={({ detail }) => setTimecardPageIndex(detail.currentPageIndex)}
            pagesCount={Math.ceil(transformedEntries.length / timecardPreferences.pageSize)}
            ariaLabels={{
              nextPageLabel: "Next page",
              previousPageLabel: "Previous page",
              pageLabel: pageNumber => `Page ${pageNumber} of all pages`
            }}
          />
        }
        preferences={
          <CollectionPreferences
            title="Preferences"
            confirmLabel="Confirm"
            cancelLabel="Cancel"
            preferences={timecardPreferences}
            onConfirm={({ detail }) => setTimecardPreferences(detail)}
            pageSizePreference={{
              title: "Page size",
              options: [
                { value: 10, label: "10 entries" },
                { value: 25, label: "25 entries" },
                { value: 50, label: "50 entries" },
                { value: 100, label: "100 entries" }
              ]
            }}
            visibleContentPreference={{
              title: "Select visible columns",
              options: [
                {
                  label: "Entry properties",
                  options: updatedColumnDefinitions.map(({ id, header }) => ({
                    id,
                    label: header
                  }))
                }
              ]
            }}
          />
        }
        empty={
          <Box textAlign="center" color="inherit">
            <b>No timecard entries found</b>
          </Box>
        }
        header={
          <Header
            counter={`(${entries.length})`}
            description="Individual timecard entries with pagination and sorting support"
          >
            Timecard Entries
          </Header>
        }
      />
    );
  };

  // Tab content renderers
  const renderOverviewTab = () => {
    if (!job?.result) return null;

    return (
      <SpaceBetween size="m">
        <Container
          header={<Header variant="h3">Extraction Summary</Header>}
        >
          <ColumnLayout columns={2}>
            <KeyValuePairs
              columns={1}
              items={[
                {
                  label: 'Employee Count',
                  value: job.result.extracted_data?.employee_count || 0
                },
                {
                  label: 'Total Timecards',
                  value: job.result.extracted_data?.total_timecards || 0
                },
                {
                  label: 'Unique Days',
                  value: job.result.extracted_data?.unique_days || job.result.extracted_data?.total_days || 0
                }
              ]}
            />
            <KeyValuePairs
              columns={1}
              items={[
                {
                  label: 'Total Wage',
                  value: `$${(job.result.extracted_data?.total_wage || 0).toFixed(2)}`
                },
                {
                  label: 'Average Daily Rate',
                  value: `$${(job.result.extracted_data?.average_daily_rate || 0).toFixed(2)}`
                },
                {
                  label: 'Pay Period',
                  value: job.result.extracted_data?.pay_period_start && job.result.extracted_data?.pay_period_end
                    ? `${job.result.extracted_data.pay_period_start} to ${job.result.extracted_data.pay_period_end}`
                    : 'N/A'
                },
                {
                  label: 'Extraction Method',
                  value: job.result.extracted_data?.extraction_method || 'N/A'
                }
              ]}
            />
          </ColumnLayout>
        </Container>
        {renderValidationResults()}
      </SpaceBetween>
    );
  };

  const renderValidationResults = () => {
    if (!job?.result?.validation) return null;

    const validation = job.result.validation;

    return (
      <SpaceBetween size="m">
        <Container
          header={<Header variant="h3">Validation Summary</Header>}
        >
          <ColumnLayout columns={2}>
            <KeyValuePairs
              columns={1}
              items={[
                {
                  label: 'Validation Result',
                  value: (
                    <StatusIndicator
                      type={validation.validation_result === 'VALID' ? 'success' :
                        validation.validation_result === 'INVALID' ? 'error' : 'warning'}
                    >
                      {validation.validation_result}
                    </StatusIndicator>
                  )
                },
                {
                  label: 'Employee',
                  value: validation.employee_name || 'N/A'
                },
                {
                  label: 'Unique Days',
                  value: validation.unique_days || validation.total_days || 0
                },
                {
                  label: 'Average Daily Rate',
                  value: `$${(validation.average_daily_rate || 0).toFixed(2)}`
                }
              ]}
            />
            <KeyValuePairs
              columns={1}
              items={[
                {
                  label: 'Total Wage',
                  value: `$${(validation.total_wage || 0).toFixed(2)}`
                },
                {
                  label: 'Weekly Equivalent',
                  value: `$${(validation.weekly_equivalent || 0).toFixed(2)}`
                },
                {
                  label: 'Salary Exempt',
                  value: validation.is_salary_exempt ? 'Yes' : 'No'
                },
                {
                  label: 'Requires Review',
                  value: validation.requires_human_review ? 
                    (validation.review_completed ? 'Completed' : 'Yes') : 'No'
                }
              ]}
            />
          </ColumnLayout>
        </Container>

        {validation.validation_issues && validation.validation_issues.length > 0 && (
          <Container
            header={<Header variant="h3">Validation Issues</Header>}
          >
            <SpaceBetween size="xs">
              {validation.validation_issues.map((issue, index) => (
                <Alert key={index} type="warning">
                  {issue}
                </Alert>
              ))}
            </SpaceBetween>
          </Container>
        )}

        {validation.next_actions && validation.next_actions.length > 0 && (
          <Container
            header={<Header variant="h3">Recommended Actions</Header>}
          >
            <ul>
              {validation.next_actions.map((action, index) => (
                <li key={index}>{action}</li>
              ))}
            </ul>
          </Container>
        )}

        {validation.compliance_summary && (
          <Container
            header={<Header variant="h3">Compliance Summary</Header>}
          >
            <Box>{validation.compliance_summary}</Box>
          </Container>
        )}
      </SpaceBetween>
    );
  };

  const renderMarkdownTab = () => {
    if (!job?.result?.markdown_preview) return (
      <Container>
        <Box textAlign="center" padding={{ vertical: "xxl" }}>
          <Box variant="p" color="text-body-secondary">
            No markdown data available
          </Box>
        </Box>
      </Container>
    );

    return (
      <Container
        header={
          <Header
            variant="h3"
            actions={
              <Button
                iconName="copy"
                onClick={() => {
                  navigator.clipboard.writeText(job.result.markdown_preview || '');
                  addNotification({
                    type: 'success',
                    header: 'Copied to clipboard',
                    content: 'Markdown data has been copied to clipboard'
                  });
                }}
              >
                Copy Raw
              </Button>
            }
          >
            Markdown Preview
          </Header>
        }
      >
        <div style={{
          maxHeight: '600px',
          overflow: 'auto',
          border: '1px solid #e1e4e8',
          borderRadius: '6px',
          backgroundColor: '#fff'
        }}>
          <Box padding={{ vertical: 'm', horizontal: 'm' }}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({ node, ...props }) => (
                  <div style={{ overflowX: 'auto', marginBottom: '1rem' }}>
                    <table style={{
                      borderCollapse: 'collapse',
                      minWidth: '100%',
                      whiteSpace: 'nowrap'
                    }} {...props} />
                  </div>
                ),
                th: ({ node, ...props }) => (
                  <th style={{
                    border: '1px solid #ddd',
                    padding: '8px 12px',
                    backgroundColor: '#f5f5f5',
                    textAlign: 'left',
                    fontWeight: 'bold',
                    minWidth: '100px'
                  }} {...props} />
                ),
                td: ({ node, ...props }) => (
                  <td style={{
                    border: '1px solid #ddd',
                    padding: '8px 12px',
                    maxWidth: '200px',
                    wordWrap: 'break-word',
                    whiteSpace: 'pre-wrap'
                  }} {...props} />
                ),
                h1: ({ node, ...props }) => (
                  // eslint-disable-next-line jsx-a11y/heading-has-content
                  <h1 style={{
                    fontSize: '1.5rem',
                    marginBottom: '1rem',
                    borderBottom: '2px solid #eee',
                    paddingBottom: '0.5rem'
                  }} {...props} />
                ),
                h2: ({ node, ...props }) => (
                  // eslint-disable-next-line jsx-a11y/heading-has-content
                  <h2 style={{
                    fontSize: '1.25rem',
                    marginBottom: '0.75rem',
                    borderBottom: '1px solid #eee',
                    paddingBottom: '0.25rem'
                  }} {...props} />
                ),
                h3: ({ node, ...props }) => (
                  // eslint-disable-next-line jsx-a11y/heading-has-content
                  <h3 style={{
                    fontSize: '1.1rem',
                    marginBottom: '0.5rem',
                    color: '#333'
                  }} {...props} />
                ),
                p: ({ node, ...props }) => (
                  <p style={{
                    marginBottom: '1rem',
                    lineHeight: '1.6',
                    wordWrap: 'break-word'
                  }} {...props} />
                ),
                code: ({ node, inline, ...props }) => (
                  inline ? (
                    <code style={{
                      backgroundColor: '#f6f8fa',
                      padding: '2px 4px',
                      borderRadius: '3px',
                      fontSize: '0.9em'
                    }} {...props} />
                  ) : (
                    <code style={{
                      display: 'block',
                      backgroundColor: '#f6f8fa',
                      padding: '12px',
                      borderRadius: '6px',
                      overflow: 'auto',
                      fontSize: '0.9em'
                    }} {...props} />
                  )
                )
              }}
            >
              {job.result.markdown_preview}
            </ReactMarkdown>
          </Box>
        </div>
      </Container>
    );
  };

  if (loading) {
    return (
      <SpaceBetween size="l">
        <Header variant="h1">Job Details</Header>
        <Container>
          <Box textAlign="center" padding={{ vertical: "xxl" }}>
            <SpaceBetween size="m">
              <StatusIndicator type="loading">
                <Box fontSize="heading-m">Loading job details...</Box>
              </StatusIndicator>
              <Box variant="p" color="text-body-secondary">
                Please wait while we fetch the job information.
              </Box>
            </SpaceBetween>
          </Box>
        </Container>
      </SpaceBetween>
    );
  }

  if (error) {
    return (
      <SpaceBetween size="l">
        <Header
          variant="h1"
          actions={
            <Button variant="primary" onClick={() => navigate('/jobs')}>
              Back to Jobs
            </Button>
          }
        >
          Job Details
        </Header>

        <Container>
          <SpaceBetween size="l">
            <Box textAlign="center" padding={{ vertical: "xxl" }}>
              <SpaceBetween size="m">
                <Box>
                  <StatusIndicator type="error" iconAriaLabel="Error">
                    <Box fontSize="heading-l" fontWeight="bold">
                      Failed to Load Job
                    </Box>
                  </StatusIndicator>
                </Box>

                <Box variant="p" color="text-body-secondary">
                  {error.type === 'network' ?
                    'Unable to connect to the server. Please check your connection and try again.' :
                    error.message
                  }
                  <br />
                  {error.status && <Box variant="small">Error code: {error.status}</Box>}
                </Box>

                <SpaceBetween direction="horizontal" size="s">
                  <Button
                    variant="primary"
                    iconName="refresh"
                    onClick={() => {
                      setLoading(true);
                      setError(null);
                      fetchJob();
                    }}
                  >
                    Try Again
                  </Button>
                  <Button
                    iconName="external"
                    onClick={() => navigate('/jobs')}
                  >
                    Back to Jobs
                  </Button>
                </SpaceBetween>
              </SpaceBetween>
            </Box>
          </SpaceBetween>
        </Container>
      </SpaceBetween>
    );
  }

  if (!job) {
    return (
      <SpaceBetween size="l">
        <Header
          variant="h1"
          actions={
            <Button variant="primary" onClick={() => navigate('/jobs')}>
              Back to Jobs
            </Button>
          }
        >
          Job Details
        </Header>

        <Container>
          <SpaceBetween size="l">
            <Box textAlign="center" padding={{ vertical: "xxl" }}>
              <SpaceBetween size="m">
                <Box>
                  <StatusIndicator type="error" iconAriaLabel="Error">
                    <Box fontSize="heading-l" fontWeight="bold">
                      Job Not Found
                    </Box>
                  </StatusIndicator>
                </Box>

                <Box variant="p" color="text-body-secondary">
                  The job you're looking for doesn't exist or may have been deleted.
                  This could happen if the job was cleaned up or the ID is incorrect.
                </Box>

                <Box variant="small" color="text-body-secondary">
                  Job ID: <Box variant="code" display="inline">{jobId}</Box>
                </Box>

                <SpaceBetween direction="horizontal" size="s">
                  <Button
                    variant="primary"
                    iconName="external"
                    onClick={() => navigate('/jobs')}
                  >
                    View All Jobs
                  </Button>
                  <Button
                    iconName="upload"
                    onClick={() => navigate('/upload')}
                  >
                    Upload New File
                  </Button>
                </SpaceBetween>
              </SpaceBetween>
            </Box>
          </SpaceBetween>
        </Container>
      </SpaceBetween>
    );
  }

  return (
    <SpaceBetween size="l">
      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            {job?.result?.validation?.requires_human_review && 
             !job?.result?.validation?.review_completed && (
              <Button 
                variant="primary" 
                onClick={handleCompleteReview}
                loading={completingReview}
              >
                Complete Review
              </Button>
            )}
            <Button onClick={fetchJob}>Refresh</Button>
            {job?.status === 'pending' && (
              <Button onClick={() => setShowCancelModal(true)}>
                Cancel Job
              </Button>
            )}
            {job?.status === 'processing' && (
              <Button onClick={() => setShowStopModal(true)}>
                Stop Job
              </Button>
            )}
            {['completed', 'failed', 'cancelled'].includes(job?.status) && (
              <Button onClick={() => setShowDeleteModal(true)}>
                Delete Job
              </Button>
            )}
            <Button variant="link" onClick={() => navigate('/jobs')}>
              Back to Jobs
            </Button>
          </SpaceBetween>
        }
      >
        Job Details: {job.file_name || 'Unknown File'}
      </Header>

      {/* Job Overview */}
      <Container>
        <ColumnLayout columns={3}>
          <div>
            <Box variant="awsui-key-label">Status</Box>
            <StatusIndicator type={jobService.getStatusColor(job?.status || 'unknown')}>
              {job?.status ? job.status.charAt(0).toUpperCase() + job.status.slice(1) : 'Unknown'}
            </StatusIndicator>
          </div>
          <div>
            <Box variant="awsui-key-label">File Size</Box>
            <Box>{jobService.formatFileSize(job.file_size || 0)}</Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Job ID</Box>
            <Box fontFamily="monospace">{job.id}</Box>
          </div>
        </ColumnLayout>
      </Container>

      {/* Progress */}
      {job?.status === 'processing' && (
        <Container>
          <ProgressBar
            value={job.progress || 0}
            label="Processing Progress"
            description="Processing timecard data..."
          />
        </Container>
      )}

      {/* Error Display */}
      {job.error && (
        <Alert type="error" header="Job Failed">
          {job.error}
        </Alert>
      )}

      {/* Timing Information */}
      <Container
        header={<Header variant="h2">Timing Information</Header>}
      >
        <ColumnLayout columns={3}>
          <KeyValuePairs
            columns={1}
            items={[
              { label: 'Created', value: formatTime(job.created_at) },
              { label: 'Updated', value: formatTime(job.updated_at) }
            ]}
          />
          <KeyValuePairs
            columns={1}
            items={[
              { label: 'Completed', value: formatTime(job.completed_at) },
              {
                label: 'Duration',
                value: calculateDuration(job.created_at, job.completed_at)
              }
            ]}
          />
          <KeyValuePairs
            columns={1}
            items={[
              { label: 'Status', value: job?.status ? job.status.charAt(0).toUpperCase() + job.status.slice(1) : 'Unknown' }
            ]}
          />
        </ColumnLayout>
      </Container>

      {/* Results Tabs */}
      {job.result && (
        <Container>
          <Tabs
            activeTabId={activeTab}
            onChange={({ detail }) => setActiveTab(detail.activeTabId)}
            tabs={[
              {
                id: 'overview',
                label: 'Overview'
              },
              {
                id: 'timecard-data',
                label: 'Timecard Data'
              },
              {
                id: 'markdown-data',
                label: 'Markdown Data'
              },
              {
                id: 'raw-data',
                label: 'Raw Data'
              }
            ]}
          />

          {/* Tab Content - Conditionally Rendered for Performance */}
          {activeTab === 'overview' && renderOverviewTab()}

          {activeTab === 'timecard-data' && renderTimecardData()}

          {activeTab === 'markdown-data' && renderMarkdownTab()}

          {activeTab === 'raw-data' && (
            <Container
              header={
                <Header
                  variant="h3"
                  actions={
                    <Button
                      iconName="copy"
                      onClick={() => {
                        navigator.clipboard.writeText(JSON.stringify(job.result, null, 2));
                        addNotification({
                          type: 'success',
                          header: 'Copied to clipboard',
                          content: 'Raw data has been copied to clipboard'
                        });
                      }}
                    >
                      Copy
                    </Button>
                  }
                >
                  Raw JSON Data
                </Header>
              }
            >
              <CodeView
                content={JSON.stringify(job.result, null, 2)}
                highlight={jsonHighlight}
              />
            </Container>
          )}
        </Container>
      )}

      {/* Cancel Job Modal */}
      <Modal
        visible={showCancelModal}
        onDismiss={() => setShowCancelModal(false)}
        header="Cancel Job"
        closeAriaLabel="Close modal"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowCancelModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleCancelJob}>
                Confirm
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          <Box variant="span">
            Are you sure you want to cancel this job?
          </Box>
          <Alert type="warning">
            This action cannot be undone. The job will be marked as cancelled and removed from the processing queue.
          </Alert>
        </SpaceBetween>
      </Modal>

      {/* Stop Job Modal */}
      <Modal
        visible={showStopModal}
        onDismiss={() => setShowStopModal(false)}
        header="Stop Job"
        closeAriaLabel="Close modal"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowStopModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleStopJob}>
                Stop Job
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          <Box variant="span">
            Are you sure you want to stop this processing job?
          </Box>
          <Alert type="warning">
            This will immediately stop the job processing. The job will be marked as cancelled.
          </Alert>
        </SpaceBetween>
      </Modal>

      {/* Delete Job Modal */}
      <Modal
        visible={showDeleteModal}
        onDismiss={() => setShowDeleteModal(false)}
        header="Delete Job"
        closeAriaLabel="Close modal"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowDeleteModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleDeleteJob}>
                Delete Job
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          <Box variant="span">
            Are you sure you want to permanently delete this job?
          </Box>
          <Alert type="error">
            This action cannot be undone. All job data and results will be permanently deleted.
          </Alert>
        </SpaceBetween>
      </Modal>
    </SpaceBetween>
  );
};

export default JobDetails;