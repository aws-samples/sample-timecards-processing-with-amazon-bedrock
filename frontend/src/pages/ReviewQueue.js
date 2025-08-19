import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table,
  Header,
  SpaceBetween,
  Button,
  StatusIndicator,
  Box,
  Pagination,
  CollectionPreferences,
  PropertyFilter,
  ColumnLayout,
  Container,
  Link,
  Alert
} from '@cloudscape-design/components';
import { jobService } from '../services/jobService';

const ReviewQueue = ({ addNotification }) => {
  const navigate = useNavigate();
  const [reviewItems, setReviewItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedItems, setSelectedItems] = useState([]);
  const [preferences, setPreferences] = useState({
    pageSize: 20,
    visibleContent: ['employee', 'file_name', 'unique_days', 'daily_rate', 'total_wage', 'issues', 'created_at']
  });
  const [filtering, setFiltering] = useState({
    tokens: [],
    operation: 'and'
  });
  const [currentPageIndex, setCurrentPageIndex] = useState(1);
  const [errorCount, setErrorCount] = useState(0);
  const [hasError, setHasError] = useState(false);
  const [completingReviews, setCompletingReviews] = useState(false);

  const fetchReviewQueue = useCallback(async () => {
    // Skip if we've had too many errors
    if (errorCount >= 5) {
      setHasError(true);
      return;
    }

    try {
      const data = await jobService.getReviewQueue();
      setReviewItems(data.review_queue || []);
      setLoading(false);
      setErrorCount(0); // Reset error count on success
      setHasError(false);
    } catch (error) {
      console.error('Failed to fetch review queue:', error);
      const newErrorCount = errorCount + 1;
      setErrorCount(newErrorCount);
      
      // Only show notification for first error to avoid spam
      if (errorCount === 0) {
        addNotification({
          type: 'error',
          header: 'Review queue temporarily unavailable',
          content: 'The review queue service is experiencing issues. Please try again later.'
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
    fetchReviewQueue();
    
    // Only set up polling if we don't have persistent errors
    if (!hasError) {
      const interval = setInterval(() => {
        if (errorCount < 5) {
          fetchReviewQueue();
        }
      }, 30000); // Refresh every 30 seconds (reduced frequency)
      return () => clearInterval(interval);
    }
  }, [fetchReviewQueue, hasError, errorCount]);

  const formatTime = (dateString) => {
    if (!dateString) return 'N/A';

    const date = new Date(dateString);
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

  const getFilteredItems = () => {
    let filtered = [...reviewItems];

    filtering.tokens.forEach(token => {
      const { propertyKey, value, operator } = token;

      filtered = filtered.filter(item => {
        const itemValue = item[propertyKey];

        switch (operator) {
          case '=':
            return itemValue === value;
          case '!=':
            return itemValue !== value;
          case ':':
            return String(itemValue).toLowerCase().includes(value.toLowerCase());
          case '!:':
            return !String(itemValue).toLowerCase().includes(value.toLowerCase());
          default:
            return true;
        }
      });
    });

    return filtered;
  };

  const getPaginatedItems = () => {
    const filtered = getFilteredItems();
    const startIndex = (currentPageIndex - 1) * preferences.pageSize;
    const endIndex = startIndex + preferences.pageSize;
    return filtered.slice(startIndex, endIndex);
  };

  const handleBulkCompleteReview = async () => {
    if (selectedItems.length === 0) {
      addNotification({
        type: 'warning',
        header: 'No items selected',
        content: 'Please select items to complete review for'
      });
      return;
    }

    setCompletingReviews(true);
    try {
      const jobIds = selectedItems.map(item => item.job_id);
      const result = await jobService.bulkCompleteReview(jobIds);
      
      addNotification({
        type: 'success',
        header: 'Reviews completed',
        content: result.message
      });

      // Clear selection and refresh
      setSelectedItems([]);
      fetchReviewQueue();
    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Failed to complete reviews',
        content: error.message
      });
    } finally {
      setCompletingReviews(false);
    }
  };

  const columnDefinitions = [
    {
      id: 'employee',
      header: 'Employee',
      cell: item => item.employee_name || 'Unknown',
      sortingField: 'employee_name'
    },
    {
      id: 'file_name',
      header: 'File Name',
      cell: item => (
        <Link href={`/jobs/${item.job_id}`} onFollow={(event) => {
          event.preventDefault();
          navigate(`/jobs/${item.job_id}`);
        }}>
          {item.file_name || 'Unknown'}
        </Link>
      ),
      sortingField: 'file_name'
    },
    {
      id: 'unique_days',
      header: 'Unique Days',
      cell: item => item.unique_days || item.total_days || 0,
      sortingField: 'unique_days'
    },
    {
      id: 'daily_rate',
      header: 'Daily Rate',
      cell: item => `$${(item.average_daily_rate || 0).toFixed(2)}`,
      sortingField: 'average_daily_rate'
    },
    {
      id: 'total_wage',
      header: 'Total Wage',
      cell: item => `$${(item.total_wage || 0).toFixed(2)}`,
      sortingField: 'total_wage'
    },
    {
      id: 'issues',
      header: 'Issues',
      cell: item => {
        const issues = item.validation_issues || [];
        if (issues.length === 0) return '0 issues';
        if (issues.length === 1) return issues[0];
        return `${issues.length} issues`;
      }
    },
    {
      id: 'status',
      header: 'Status',
      cell: item => (
        <StatusIndicator type="warning">
          Pending Review
        </StatusIndicator>
      )
    },
    {
      id: 'created_at',
      header: 'Created',
      cell: item => formatTime(item.created_at),
      sortingField: 'created_at'
    }

  ];

  const propertyFilteringProperties = [
    {
      key: 'employee_name',
      operators: [':', '!:', '=', '!='],
      propertyLabel: 'Employee',
      groupValuesLabel: 'Employee values'
    },
    {
      key: 'file_name',
      operators: [':', '!:', '=', '!='],
      propertyLabel: 'File Name',
      groupValuesLabel: 'File name values'
    }
  ];

  const filteredItems = getFilteredItems();
  const paginatedItems = getPaginatedItems();

  if (hasError) {
    return (
      <SpaceBetween size="l">
        <Header variant="h1">Review Queue</Header>
        <Alert
          type="error"
          header="Service Unavailable"
          action={
            <Button
              onClick={() => {
                setErrorCount(0);
                setHasError(false);
                fetchReviewQueue();
              }}
            >
              Retry
            </Button>
          }
        >
          The review queue service is temporarily unavailable. This may be due to database connectivity issues.
        </Alert>
      </SpaceBetween>
    );
  }

  return (
    <SpaceBetween size="l">
      <Header
        variant="h1"
        description="Items requiring human review due to validation issues"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            {selectedItems.length > 0 && (
              <Button
                variant="primary"
                onClick={handleBulkCompleteReview}
                loading={completingReviews}
                disabled={selectedItems.length === 0}
              >
                Complete {selectedItems.length} Review{selectedItems.length !== 1 ? 's' : ''}
              </Button>
            )}
            <Button onClick={fetchReviewQueue} loading={loading}>
              Refresh
            </Button>
          </SpaceBetween>
        }
        counter={`(${filteredItems.length})`}
      >
        Review Queue
      </Header>

      {/* Summary Stats */}
      {reviewItems.length > 0 && (
        <Container>
          <ColumnLayout columns={4} variant="text-grid">
            <div>
              <Box variant="awsui-key-label">Total Items</Box>
              <Box variant="awsui-value-large">{reviewItems.length}</Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Total Wage Value</Box>
              <Box variant="awsui-value-large">
                ${reviewItems.reduce((sum, item) => sum + (item.total_wage || 0), 0).toFixed(2)}
              </Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Avg Daily Rate</Box>
              <Box variant="awsui-value-large">
                ${(reviewItems.reduce((sum, item) => sum + (item.average_daily_rate || 0), 0) / reviewItems.length).toFixed(2)}
              </Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Total Issues</Box>
              <Box variant="awsui-value-large">
                {reviewItems.reduce((sum, item) => sum + (item.validation_issues || []).length, 0)}
              </Box>
            </div>
          </ColumnLayout>
        </Container>
      )}

      <Table
        columnDefinitions={columnDefinitions}
        items={paginatedItems}
        loading={loading}
        loadingText="Loading review items..."
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        selectionType="multi"
        ariaLabels={{
          selectionGroupLabel: "Items selection",
          allItemsSelectionLabel: ({ selectedItems }) =>
            `${selectedItems.length} ${selectedItems.length === 1 ? "item" : "items"
            } selected`,
          itemSelectionLabel: ({ selectedItems }, item) => {
            const isItemSelected = selectedItems.filter(
              i => i.id === item.id
            ).length;
            return `${item.employee_name} is ${isItemSelected ? "" : "not "
              }selected`;
          }
        }}
        header={
          selectedItems.length > 0 ? (
            <Header
              counter={`(${selectedItems.length} selected)`}
              actions={
                <SpaceBetween direction="horizontal" size="xs">
                  <Button
                    variant="primary"
                    onClick={handleBulkCompleteReview}
                    loading={completingReviews}
                  >
                    Complete Selected Reviews
                  </Button>
                  <Button onClick={() => setSelectedItems([])}>
                    Clear Selection
                  </Button>
                </SpaceBetween>
              }
            >
              Selected Items
            </Header>
          ) : undefined
        }
        filter={
          <PropertyFilter
            query={filtering}
            onChange={({ detail }) => {
              setFiltering(detail);
              setCurrentPageIndex(1);
            }}
            countText={`${filteredItems.length} matches`}
            expandToViewport={true}
            filteringProperties={propertyFilteringProperties}
            filteringPlaceholder="Find review items"
          />
        }
        pagination={
          <Pagination
            currentPageIndex={currentPageIndex}
            onChange={({ detail }) => setCurrentPageIndex(detail.currentPageIndex)}
            pagesCount={Math.ceil(filteredItems.length / preferences.pageSize)}
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
                { value: 10, label: "10 items" },
                { value: 20, label: "20 items" },
                { value: 50, label: "50 items" },
                { value: 100, label: "100 items" }
              ]
            }}
            visibleContentPreference={{
              title: "Select visible columns",
              options: [
                {
                  label: "Review item properties",
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
            <b>No items in review queue</b>
            <Box variant="p" color="inherit">
              All processed timecards are compliant and don't require human review.
            </Box>
          </Box>
        }
      />
    </SpaceBetween>
  );
};

export default ReviewQueue;