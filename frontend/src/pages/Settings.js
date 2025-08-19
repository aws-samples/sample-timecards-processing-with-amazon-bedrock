import React, { useState, useEffect, useCallback } from 'react';
import {
  Header,
  SpaceBetween,
  Container,
  FormField,
  Input,
  Button,
  Alert,
  Box,
  ColumnLayout,
  Toggle,
  Select
} from '@cloudscape-design/components';
import { jobService } from '../services/jobService';

const Settings = ({ addNotification }) => {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [systemInfo, setSystemInfo] = useState({});
  const [automatedReasoningStatus, setAutomatedReasoningStatus] = useState({});
  const [errorCount, setErrorCount] = useState(0);
  const [hasError, setHasError] = useState(false);

  const fetchSettings = useCallback(async () => {
    // Skip if we've had too many errors
    if (errorCount >= 3) {
      setHasError(true);
      return;
    }

    try {
      // First check if backend is reachable
      const response = await jobService.getSettings();

      // Transform backend settings to frontend format
      const transformedSettings = {
        autoCleanupEnabled: response.auto_cleanup_enabled || false,
        cleanupDays: response.cleanup_after_days || 7,
        maxConcurrentJobs: response.max_concurrent_jobs || 3,
        notificationsEnabled: response.enable_notifications || true,

        awsRegion: getRegionOption(response.aws_region || 'us-west-2'),
        claudeModel: getModelOption(response.bedrock_model_id || 'us.anthropic.claude-sonnet-4-20250514-v1:0'),
        federalMinimumWage: response.federal_minimum_wage || 7.25,
        overtimeThreshold: response.overtime_threshold_hours || 40,
        salaryExemptThreshold: response.salary_exempt_threshold_weekly || 684,
        maxRecommendedHours: response.max_recommended_hours_weekly || 60,
        validationRules: response.validation_rules || {},
        reviewTriggers: response.review_triggers || {}
      };

      setSettings(transformedSettings);
      setSystemInfo(response.system_info || {});
      setAutomatedReasoningStatus(response.automated_reasoning_status || {});
      setLoading(false);
      setErrorCount(0); // Reset error count on success
      setHasError(false);
    } catch (error) {
      console.error('Failed to fetch settings:', error);
      const newErrorCount = errorCount + 1;
      setErrorCount(newErrorCount);

      // Only show notification for first error to avoid spam
      if (errorCount === 0) {
        // Provide more specific error messages
        let errorMessage = 'Settings service is temporarily unavailable';
        if (error.code === 'NETWORK_ERROR' || error.message === 'Network Error') {
          errorMessage = 'Cannot connect to backend server. Please ensure the backend is running.';
        } else if (error.response?.status === 500) {
          errorMessage = 'Server error occurred while loading settings.';
        } else if (error.response?.data?.error) {
          errorMessage = error.response.data.error;
        } else {
          errorMessage = error.message;
        }

        addNotification({
          type: 'error',
          header: 'Settings temporarily unavailable',
          content: errorMessage
        });
      }

      // Stop retrying after 3 errors
      if (newErrorCount >= 3) {
        setHasError(true);
      }

      // Set default settings to prevent UI errors
      setSettings({
        autoCleanupEnabled: true,
        cleanupDays: 7,
        maxConcurrentJobs: 3,
        notificationsEnabled: true,
        awsRegion: { label: 'US West 2', value: 'us-west-2' },
        claudeModel: { label: 'Claude Sonnet 4', value: 'us.anthropic.claude-sonnet-4-20250514-v1:0' },
        federalMinimumWage: 7.25,
        overtimeThreshold: 40,
        salaryExemptThreshold: 684,
        maxRecommendedHours: 60,
        validationRules: {},
        reviewTriggers: {}
      });

      setLoading(false);
    }
  }, [addNotification, errorCount]);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  // Auto-check Automated Reasoning progress when status is 'creating'
  useEffect(() => {
    if (automatedReasoningStatus.status !== 'creating') {
      return;
    }

    const checkProgress = async () => {
      try {
        const response = await fetch('/api/automated-reasoning/check-progress', {
          method: 'POST'
        });
        const result = await response.json();
        
        if (result.status === 'success' && result.result?.status !== 'creating') {
          // Status changed, refresh settings
          fetchSettings();
        }
      } catch (error) {
        console.error('Auto progress check failed:', error);
      }
    };

    // Check immediately, then every 30 seconds
    checkProgress();
    const interval = setInterval(checkProgress, 30000);
    
    return () => clearInterval(interval);
  }, [automatedReasoningStatus.status, fetchSettings]);



  const getRegionOption = (value) => {
    const options = [
      { label: 'US East 1', value: 'us-east-1' },
      { label: 'US West 2', value: 'us-west-2' },
      { label: 'EU West 1', value: 'eu-west-1' },
      { label: 'AP Southeast 1', value: 'ap-southeast-1' }
    ];
    return options.find(opt => opt.value === value) || options[1];
  };

  const getModelOption = (value) => {
    const options = [
      { label: 'Claude Opus 4.1', value: 'us.anthropic.claude-opus-4-1-20250805-v1:0' },
      { label: 'Claude Sonnet 4', value: 'us.anthropic.claude-sonnet-4-20250514-v1:0' },
      { label: 'Claude 3.7 Sonnet', value: 'us.anthropic.claude-3-7-sonnet-20250219-v1:0' }
    ];
    return options.find(opt => opt.value === value) || options[1];
  };

  const getAutomatedReasoningStatusDisplay = (status) => {
    switch (status) {
      case 'ready':
        return 'Active';
      case 'creating':
        return 'Setting Up';
      case 'failed':
        return 'Failed';
      case 'not_configured':
        return 'Not Configured';
      default:
        return 'Unknown';
    }
  };

  const handleCleanup = async () => {
    try {
      const result = await jobService.cleanupQueue(settings.cleanupDays);
      addNotification({
        type: 'success',
        header: 'Cleanup completed',
        content: result.message
      });
    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Cleanup failed',
        content: error.message
      });
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Transform frontend settings to backend format
      const backendSettings = {
        auto_cleanup_enabled: settings.autoCleanupEnabled,
        cleanup_after_days: settings.cleanupDays,
        max_concurrent_jobs: settings.maxConcurrentJobs,
        enable_notifications: settings.notificationsEnabled,
        aws_region: settings.awsRegion?.value || 'us-west-2',
        bedrock_model_id: settings.claudeModel?.value || 'us.anthropic.claude-sonnet-4-20250514-v1:0',
        federal_minimum_wage: settings.federalMinimumWage,
        overtime_threshold_hours: settings.overtimeThreshold,
        salary_exempt_threshold_weekly: settings.salaryExemptThreshold,
        max_recommended_hours_weekly: settings.maxRecommendedHours,
        validation_rules: settings.validationRules,
        review_triggers: settings.reviewTriggers
      };

      await jobService.updateSettings(backendSettings);

      addNotification({
        type: 'success',
        header: 'Settings saved',
        content: 'Your settings have been updated successfully'
      });
    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Failed to save settings',
        content: error.message
      });
    } finally {
      setSaving(false);
    }
  };



  const regionOptions = [
    { label: 'US East 1', value: 'us-east-1' },
    { label: 'US West 2', value: 'us-west-2' },
    { label: 'EU West 1', value: 'eu-west-1' },
    { label: 'AP Southeast 1', value: 'ap-southeast-1' }
  ];



  if (hasError) {
    return (
      <SpaceBetween size="l">
        <Header variant="h1">Settings</Header>
        <Alert
          type="error"
          header="Settings Service Unavailable"
          action={
            <Button
              onClick={() => {
                setErrorCount(0);
                setHasError(false);
                fetchSettings();
              }}
            >
              Retry
            </Button>
          }
        >
          The settings service is temporarily unavailable. This may be due to database connectivity issues.
        </Alert>
      </SpaceBetween>
    );
  }

  if (loading) {
    return <Box>Loading settings...</Box>;
  }

  return (
    <SpaceBetween size="l">
      <Header
        variant="h1"
        description="Configure system settings and preferences"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button onClick={handleSave} loading={saving} variant="primary">
              Save Settings
            </Button>
          </SpaceBetween>
        }
      >
        Settings
      </Header>

      {/* Job Processing Settings */}
      <Container
        header={
          <Header variant="h2">
            Job Processing
          </Header>
        }
      >
        <SpaceBetween size="m">
          <ColumnLayout columns={2}>
            <FormField
              label="Maximum Concurrent Jobs"
              description="Number of jobs that can be processed simultaneously"
            >
              <Input
                value={settings.maxConcurrentJobs?.toString() || '3'}
                onChange={({ detail }) =>
                  setSettings(prev => ({
                    ...prev,
                    maxConcurrentJobs: parseInt(detail.value) || 1
                  }))
                }
                type="number"
                inputMode="numeric"
              />
            </FormField>


          </ColumnLayout>

          <FormField
            label="Enable Notifications"
            description="Show notifications for job status changes"
          >
            <Toggle
              checked={settings.notificationsEnabled}
              onChange={({ detail }) =>
                setSettings(prev => ({
                  ...prev,
                  notificationsEnabled: detail.checked
                }))
              }
            >
              {settings.notificationsEnabled ? 'Enabled' : 'Disabled'}
            </Toggle>
          </FormField>
        </SpaceBetween>
      </Container>

      {/* AWS Configuration */}
      <Container
        header={
          <Header variant="h2">
            AWS Configuration
          </Header>
        }
      >
        <SpaceBetween size="m">
          <ColumnLayout columns={2}>
            <FormField
              label="AWS Region"
              description="Region for Bedrock and other AWS services"
            >
              <Select
                selectedOption={settings.awsRegion}
                onChange={({ detail }) =>
                  setSettings(prev => ({
                    ...prev,
                    awsRegion: detail.selectedOption
                  }))
                }
                options={regionOptions}
              />
            </FormField>

            <FormField
              label="Claude Model"
              description="AI model for timecard processing"
            >
              <Select
                selectedOption={settings.claudeModel}
                onChange={({ detail }) =>
                  setSettings(prev => ({
                    ...prev,
                    claudeModel: detail.selectedOption
                  }))
                }
                options={[
                  { label: 'Claude Opus 4.1', value: 'us.anthropic.claude-opus-4-1-20250805-v1:0' },
                  { label: 'Claude Sonnet 4', value: 'us.anthropic.claude-sonnet-4-20250514-v1:0' },
                  { label: 'Claude 3.7 Sonnet', value: 'us.anthropic.claude-3-7-sonnet-20250219-v1:0' }
                ]}
              />
            </FormField>
          </ColumnLayout>

          <Alert type="info">
            <Box variant="h4">AWS Credentials</Box>
            <Box>
              AWS credentials are configured via environment variables or IAM roles.
              Ensure your environment has access to:
            </Box>
            <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
              <li>Amazon Bedrock (for Claude models)</li>
              <li>Amazon S3 (for file storage)</li>
              <li>CloudWatch (for logging)</li>
            </ul>
          </Alert>
        </SpaceBetween>
      </Container>

      {/* Configuration Validation */}
      <Container
        header={
          <Header variant="h2">
            Configuration Validation
          </Header>
        }
      >
        <SpaceBetween size="m">
          <ColumnLayout columns={2}>
            <Box>
              <Box variant="h4">AWS Configuration Status</Box>
              <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
                <li>Credentials: {systemInfo.aws_config?.has_credentials ? 'Configured' : 'Missing'}</li>
                <li>Region: {systemInfo.aws_config?.has_region ? settings.awsRegion?.label || 'Unknown' : 'Not Set'}</li>
                <li>Bedrock Model: {systemInfo.aws_config?.bedrock_configured ? settings.claudeModel?.label || 'Unknown' : 'Not Configured'}</li>
              </ul>
            </Box>
            <Box>
              <Box variant="h4">Automated Reasoning Status</Box>
              <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
                <li>Status: {getAutomatedReasoningStatusDisplay(automatedReasoningStatus.status)}</li>
                <li>Policy ARN: {automatedReasoningStatus.policy_arn ? 'Configured' : 'Not Set'}</li>
                <li>Guardrail ID: {automatedReasoningStatus.guardrail_id ? 'Configured' : 'Not Set'}</li>
                <li>Validation Method: {automatedReasoningStatus.validation_method || 'Fallback'}</li>
              </ul>
            </Box>
          </ColumnLayout>

          {automatedReasoningStatus.status === 'creating' && (
            <Alert 
              type="info"
              action={
                <Button
                  onClick={async () => {
                    try {
                      const response = await fetch('/api/automated-reasoning/check-progress', {
                        method: 'POST'
                      });
                      const result = await response.json();
                      
                      if (result.status === 'success') {
                        // Refresh settings to get updated status
                        fetchSettings();
                        addNotification({
                          type: 'info',
                          header: 'Progress checked',
                          content: result.message
                        });
                      } else if (result.status === 'rate_limited') {
                        addNotification({
                          type: 'warning',
                          header: 'Rate limited',
                          content: result.message
                        });
                      }
                    } catch (error) {
                      addNotification({
                        type: 'error',
                        header: 'Failed to check progress',
                        content: error.message
                      });
                    }
                  }}
                >
                  Check Progress
                </Button>
              }
            >
              <Box variant="h4">Automated Reasoning Setup In Progress</Box>
              <Box>
                The system is currently setting up Automated Reasoning for enhanced mathematical validation.
                This process may take a few minutes to complete.
              </Box>
              {automatedReasoningStatus.message && (
                <Box margin={{ top: "xs" }}>
                  Status: {automatedReasoningStatus.message}
                </Box>
              )}
            </Alert>
          )}

          {automatedReasoningStatus.status === 'ready' && (
            <Alert type="success">
              <Box variant="h4">Automated Reasoning Active</Box>
              <Box>
                Mathematical validation is active using Amazon Bedrock Automated Reasoning.
                This provides up to 99% accuracy in detecting calculation errors and data inconsistencies.
              </Box>
            </Alert>
          )}

          {automatedReasoningStatus.status === 'failed' && (
            <Alert type="error">
              <Box variant="h4">Automated Reasoning Setup Failed</Box>
              <Box>
                The system failed to set up Automated Reasoning. Using fallback validation method.
              </Box>
              {automatedReasoningStatus.error && (
                <Box margin={{ top: "xs" }}>
                  Error: {automatedReasoningStatus.error}
                </Box>
              )}
            </Alert>
          )}

          {(!automatedReasoningStatus.status || automatedReasoningStatus.status === 'not_configured') && (
            <Alert type="warning">
              <Box variant="h4">Automated Reasoning Not Configured</Box>
              <Box>
                Enhanced mathematical validation is not configured. The system will use basic validation methods.
                Automated Reasoning setup will begin automatically when the application starts.
              </Box>
            </Alert>
          )}
        </SpaceBetween>
      </Container>

      {/* Data Management */}
      <Container
        header={
          <Header variant="h2">
            Data Management
          </Header>
        }
      >
        <SpaceBetween size="m">
          <ColumnLayout columns={2}>
            <FormField
              label="Auto Cleanup"
              description="Automatically clean up old completed jobs"
            >
              <Toggle
                checked={settings.autoCleanupEnabled}
                onChange={({ detail }) =>
                  setSettings(prev => ({
                    ...prev,
                    autoCleanupEnabled: detail.checked
                  }))
                }
              >
                {settings.autoCleanupEnabled ? 'Enabled' : 'Disabled'}
              </Toggle>
            </FormField>

            <FormField
              label="Cleanup After (Days)"
              description="Number of days to keep completed jobs"
            >
              <Input
                value={settings.cleanupDays?.toString() || '7'}
                onChange={({ detail }) =>
                  setSettings(prev => ({
                    ...prev,
                    cleanupDays: parseInt(detail.value) || 7
                  }))
                }
                type="number"
                inputMode="numeric"
                disabled={!settings.autoCleanupEnabled}
              />
            </FormField>
          </ColumnLayout>

          <Box>
            <Button onClick={handleCleanup}>
              Run Cleanup Now
            </Button>
            <Box variant="small" color="text-body-secondary" margin={{ top: "xs" }}>
              This will remove all completed, failed, and cancelled jobs older than {settings.cleanupDays || 7} days
            </Box>
          </Box>
        </SpaceBetween>
      </Container>

      {/* Compliance Settings */}
      <Container
        header={
          <Header variant="h2">
            Compliance Settings
          </Header>
        }
      >
        <SpaceBetween size="m">
          <ColumnLayout columns={2}>
            <FormField
              label="Federal Minimum Wage ($/hour)"
              description="Current federal minimum wage rate"
            >
              <Input
                value={settings.federalMinimumWage?.toString() || '7.25'}
                onChange={({ detail }) =>
                  setSettings(prev => ({
                    ...prev,
                    federalMinimumWage: parseFloat(detail.value) || 7.25
                  }))
                }
                type="number"
                step="0.01"
                inputMode="decimal"
              />
            </FormField>

            <FormField
              label="Overtime Threshold (hours/week)"
              description="Hours per week before overtime applies"
            >
              <Input
                value={settings.overtimeThreshold?.toString() || '40'}
                onChange={({ detail }) =>
                  setSettings(prev => ({
                    ...prev,
                    overtimeThreshold: parseInt(detail.value) || 40
                  }))
                }
                type="number"
                inputMode="numeric"
              />
            </FormField>

            <FormField
              label="Salary Exempt Threshold ($/week)"
              description="Weekly salary threshold for exempt employees"
            >
              <Input
                value={settings.salaryExemptThreshold?.toString() || '684'}
                onChange={({ detail }) =>
                  setSettings(prev => ({
                    ...prev,
                    salaryExemptThreshold: parseFloat(detail.value) || 684
                  }))
                }
                type="number"
                step="0.01"
                inputMode="decimal"
              />
            </FormField>

            <FormField
              label="Max Recommended Hours (hours/week)"
              description="Maximum recommended hours per week"
            >
              <Input
                value={settings.maxRecommendedHours?.toString() || '60'}
                onChange={({ detail }) =>
                  setSettings(prev => ({
                    ...prev,
                    maxRecommendedHours: parseInt(detail.value) || 60
                  }))
                }
                type="number"
                inputMode="numeric"
              />
            </FormField>
          </ColumnLayout>

          <Alert type="info">
            <Box variant="h4">Current Compliance Rules</Box>
            <Box>
              The system automatically validates timecards against these configured wage laws:
            </Box>
            <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
              <li>Federal minimum wage: ${settings.federalMinimumWage || 7.25}/hour</li>
              <li>Overtime threshold: {settings.overtimeThreshold || 40} hours/week</li>
              <li>Salary exempt threshold: ${settings.salaryExemptThreshold || 684}/week</li>
              <li>Maximum recommended hours: {settings.maxRecommendedHours || 60}/week</li>
            </ul>
          </Alert>

          <ColumnLayout columns={2}>
            <Box>
              <Box variant="h4">Validation Rules</Box>
              <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
                <li>Daily rate minimum wage check</li>
                <li>Excessive hours flagging</li>
                <li>Salary exempt validation</li>
                <li>Human review triggers</li>
              </ul>
            </Box>
            <Box>
              <Box variant="h4">Review Triggers</Box>
              <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
                <li>Rate below federal minimum</li>
                <li>More than {settings.maxRecommendedHours || 60} hours/week</li>
                <li>High daily rates (&gt;$2000)</li>
                <li>Salary exempt excessive hours</li>
              </ul>
            </Box>
          </ColumnLayout>
        </SpaceBetween>
      </Container>

      {/* System Information */}
      <Container
        header={
          <Header variant="h2">
            System Information
          </Header>
        }
      >
        <ColumnLayout columns={2}>
          <Box>
            <Box variant="h4">Browser Information</Box>
            <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
              <li>Current Time: {new Date().toLocaleString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                timeZoneName: 'long'
              })}</li>
              <li>Timezone: {Intl.DateTimeFormat().resolvedOptions().timeZone}</li>
              <li>Language: {navigator.language}</li>
            </ul>
          </Box>
          <Box>
            <Box variant="h4">System</Box>
            <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
              <li>Platform: {navigator.platform.includes('Mac') && navigator.userAgent.includes('ARM') ? 'Mac ARM' : navigator.platform.includes('Mac') ? 'MacIntel' : navigator.platform}</li>
              <li>Browser: {navigator.userAgent.match(/(Chrome|Firefox|Safari|Edge)\/[\d.]+/)?.[0] || 'Unknown'}</li>
            </ul>
          </Box>
        </ColumnLayout>
      </Container>
    </SpaceBetween>
  );
};

export default Settings;