import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table,
  Header,
  SpaceBetween,
  Button,
  StatusIndicator,
  Badge,
  Box,
  Pagination,
  CollectionPreferences,
  PropertyFilter,
  ProgressBar,
  Link,
  Modal,
  Alert
} from '@cloudscape-design/components';
import { jobService } from '../services/jobService';

const JobsTable = ({ addNotification }) => {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedItems, setSelectedItems] = useState([]);
  const [preferences, setPreferences] = useState({
    pageSize: 20,
    visibleContent: ['id', 'file_name', 'status', 'created_at', 'progress']
  });
  const [filtering, setFiltering] = useState({
    tokens: [],
    operation: 'and'
  });
  const [currentPageIndex, setCurrentPageIndex] = useState(1);
  const [showBulkDeleteModal, setShowBulkDeleteModal] = useState(false);
  const [deletingJobs, setDeletingJobs] = useState(false);


  const fetchJobs = useCallback(async () => {
    try {
      const data = await jobService.getJobs({ limit: 100 });
      setJobs(data.jobs || []);
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
      addNotification({
        type: 'error',
        header: 'Failed to load jobs',
        content: error.message
      });
      setLoading(false);
    }
  }, [addNotification]);

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, [fetchJobs]);



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

  const getFilteredJobs = () => {
    let filtered = [...jobs];

    // Apply property filters
    filtering.tokens.forEach(token => {
      const { propertyKey, value, operator } = token;
      
      filtered = filtered.filter(job => {
        const jobValue = job[propertyKey];
        
        switch (operator) {
          case '=':
            return jobValue === value;
          case '!=':
            return jobValue !== value;
          case ':':
            return String(jobValue).toLowerCase().includes(value.toLowerCase());
          case '!:':
            return !String(jobValue).toLowerCase().includes(value.toLowerCase());
          default:
            return true;
        }
      });
    });

    return filtered;
  };

  const getPaginatedJobs = () => {
    const filtered = getFilteredJobs();
    const startIndex = (currentPageIndex - 1) * preferences.pageSize;
    const endIndex = startIndex + preferences.pageSize;
    return filtered.slice(startIndex, endIndex);
  };

  const handleBulkDelete = () => {
    if (selectedItems.length === 0) return;
    setShowBulkDeleteModal(true);
  };

  const confirmBulkDelete = async () => {
    if (selectedItems.length === 0) return;

    try {
      setDeletingJobs(true);
      
      const jobIds = selectedItems.map(job => job.id);
      const result = await jobService.bulkDeleteJobs(jobIds);

      if (result.errors && result.errors.length > 0) {
        addNotification({
          type: 'warning',
          header: 'Partial deletion completed',
          content: `${result.deleted_count} of ${result.total_requested} jobs deleted. ${result.errors.length} errors occurred.`
        });
      } else {
        addNotification({
          type: 'success',
          header: 'Jobs deleted',
          content: `${result.deleted_count} job(s) have been deleted`
        });
      }
      
      setSelectedItems([]);
      fetchJobs();
    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Failed to delete jobs',
        content: error.message
      });
    } finally {
      setDeletingJobs(false);
      setShowBulkDeleteModal(false);
    }
  };

  const canDeleteSelected = () => {
    return selectedItems.every(job => 
      ['completed', 'failed', 'cancelled'].includes(job.status)
    );
  };

  const columnDefinitions = [
    {
      id: 'id',
      header: 'Job ID',
      cell: item => (
        <Link href={`/jobs/${item.id}`} onFollow={(event) => {
          event.preventDefault();
          navigate(`/jobs/${item.id}`);
        }}>
          {item.id.substring(0, 8)}...
        </Link>
      ),
      sortingField: 'id',
      isRowHeader: true
    },
    {
      id: 'file_name',
      header: 'File Name',
      cell: item => (
        <Link href={`/jobs/${item.id}`} onFollow={(event) => {
          event.preventDefault();
          navigate(`/jobs/${item.id}`);
        }}>
          {item.file_name || 'Unknown'}
        </Link>
      ),
      sortingField: 'file_name'
    },
    {
      id: 'status',
      header: 'Status',
      cell: item => (
        <StatusIndicator type={jobService.getStatusColor(item.status)}>
          {item.status.charAt(0).toUpperCase() + item.status.slice(1)}
        </StatusIndicator>
      ),
      sortingField: 'status'
    },

    {
      id: 'progress',
      header: 'Progress',
      cell: item => {
        if (item.status === 'processing') {
          return (
            <ProgressBar
              value={item.progress || 0}
              description="Processing..."
            />
          );
        }
        if (item.status === 'completed') {
          return <Badge color="green">100%</Badge>;
        }
        if (item.status === 'failed') {
          return <Badge color="red">Failed</Badge>;
        }
        return <Badge color="grey">-</Badge>;
      }
    },
    {
      id: 'file_size',
      header: 'File Size',
      cell: item => jobService.formatFileSize(item.file_size || 0),
      sortingField: 'file_size'
    },
    {
      id: 'created_at',
      header: 'Created',
      cell: item => formatTime(item.created_at),
      sortingField: 'created_at'
    },
    {
      id: 'updated_at',
      header: 'Updated',
      cell: item => formatTime(item.updated_at),
      sortingField: 'updated_at'
    },

  ];

  const propertyFilteringProperties = [
    {
      key: 'status',
      operators: ['=', '!='],
      propertyLabel: 'Status',
      groupValuesLabel: 'Status values'
    },

    {
      key: 'file_name',
      operators: [':', '!:', '=', '!='],
      propertyLabel: 'File Name',
      groupValuesLabel: 'File name values'
    }
  ];

  const filteredJobs = getFilteredJobs();
  const paginatedJobs = getPaginatedJobs();

  return (
    <SpaceBetween size="l">
      <Header
        variant="h1"
        description="Monitor and manage timecard processing jobs"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            {selectedItems.length > 0 && canDeleteSelected() && (
              <Button 
                onClick={handleBulkDelete}
                loading={deletingJobs}
              >
                Delete Selected ({selectedItems.length})
              </Button>
            )}
            <Button onClick={fetchJobs} loading={loading}>
              Refresh
            </Button>
            <Button variant="primary" href="/upload">
              Upload Files
            </Button>
          </SpaceBetween>
        }
        counter={`(${filteredJobs.length})`}
      >
        Jobs
      </Header>

      <Table
        columnDefinitions={columnDefinitions}
        items={paginatedJobs}
        loading={loading}
        loadingText="Loading jobs..."
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        selectionType="multi"
        ariaLabels={{
          selectionGroupLabel: "Items selection",
          allItemsSelectionLabel: ({ selectedItems }) =>
            `${selectedItems.length} ${
              selectedItems.length === 1 ? "item" : "items"
            } selected`,
          itemSelectionLabel: ({ selectedItems }, item) => {
            const isItemSelected = selectedItems.filter(
              i => i.id === item.id
            ).length;
            return `${item.file_name} is ${
              isItemSelected ? "" : "not "
            }selected`;
          }
        }}
        filter={
          <PropertyFilter
            query={filtering}
            onChange={({ detail }) => {
              setFiltering(detail);
              setCurrentPageIndex(1);
            }}
            countText={`${filteredJobs.length} matches`}
            expandToViewport={true}
            filteringProperties={propertyFilteringProperties}
            filteringPlaceholder="Find jobs"
          />
        }
        pagination={
          <Pagination
            currentPageIndex={currentPageIndex}
            onChange={({ detail }) => setCurrentPageIndex(detail.currentPageIndex)}
            pagesCount={Math.ceil(filteredJobs.length / preferences.pageSize)}
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
            preferences={preferences}
            onConfirm={({ detail }) => setPreferences(detail)}
            pageSizePreference={{
              title: "Page size",
              options: [
                { value: 10, label: "10 jobs" },
                { value: 20, label: "20 jobs" },
                { value: 50, label: "50 jobs" },
                { value: 100, label: "100 jobs" }
              ]
            }}
            visibleContentPreference={{
              title: "Select visible columns",
              options: [
                {
                  label: "Job properties",
                  options: columnDefinitions.map(({ id, header }) => ({
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
            <b>No jobs found</b>
            <Box variant="p" color="inherit">
              Upload a timecard file to create your first job.
            </Box>
          </Box>
        }
      />

      {/* Bulk Delete Modal */}
      <Modal
        visible={showBulkDeleteModal}
        onDismiss={() => setShowBulkDeleteModal(false)}
        header="Delete Selected Jobs"
        closeAriaLabel="Close modal"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowBulkDeleteModal(false)}>
                Cancel
              </Button>
              <Button 
                variant="primary" 
                onClick={confirmBulkDelete}
                loading={deletingJobs}
              >
                Delete {selectedItems.length} Job{selectedItems.length > 1 ? 's' : ''}
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          <Box variant="span">
            Are you sure you want to permanently delete {selectedItems.length} selected job{selectedItems.length > 1 ? 's' : ''}?
          </Box>
          <Alert type="error">
            This action cannot be undone. All job data and results will be permanently deleted.
          </Alert>
          <Box variant="small">
            Selected jobs:
            <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
              {selectedItems.slice(0, 5).map(job => (
                <li key={job.id}>{job.file_name}</li>
              ))}
              {selectedItems.length > 5 && (
                <li>... and {selectedItems.length - 5} more</li>
              )}
            </ul>
          </Box>
        </SpaceBetween>
      </Modal>
    </SpaceBetween>
  );
};

export default JobsTable;