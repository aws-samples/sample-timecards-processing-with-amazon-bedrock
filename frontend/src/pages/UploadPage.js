import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Header,
  SpaceBetween,
  Container,
  FormField,
  FileUpload,
  Button,
  Alert,
  ProgressBar,
  Box,
  ColumnLayout,
  StatusIndicator,
  Cards
} from '@cloudscape-design/components';
import { jobService } from '../services/jobService';

const UploadPage = ({ addNotification }) => {
  const navigate = useNavigate();
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);
  const [samples, setSamples] = useState([]);
  const [loadingSamples, setLoadingSamples] = useState(true);


  useEffect(() => {
    fetchSamples();
  }, []);

  const fetchSamples = async () => {
    try {
      const sampleFiles = await jobService.getSamples();
      setSamples(sampleFiles);
      setLoadingSamples(false);
    } catch (error) {
      console.error('Failed to fetch samples:', error);
      setLoadingSamples(false);
    }
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      addNotification({
        type: 'error',
        header: 'No file selected',
        content: 'Please select a file to upload'
      });
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setCurrentStep(0);

    try {
      const file = files[0];
      setCurrentStep(1); // File Analysis step
      
      const result = await jobService.uploadFile(file, (progress) => {
        setUploadProgress(progress);
        if (progress > 50) setCurrentStep(2); // AI Extraction step
        if (progress > 80) setCurrentStep(3); // Compliance Validation step
      });

      addNotification({
        type: 'success',
        header: 'File uploaded successfully',
        content: `Job ${result.job_id} created for ${result.file_name}`
      });

      // Reset form
      setFiles([]);
      setUploadProgress(0);
      setCurrentStep(0);

      // Navigate to job details page immediately
      navigate(`/jobs/${result.job_id}`);

    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Upload failed',
        content: error.response?.data?.error || error.message
      });
    } finally {
      setUploading(false);
      setCurrentStep(0);
    }
  };

  const handleSampleProcess = async (filename) => {
    try {
      const result = await jobService.processSample(filename);
      
      addNotification({
        type: 'success',
        header: 'Sample file queued',
        content: `Job ${result.job_id} created for ${filename}`
      });

      // Navigate to job details page immediately
      navigate(`/jobs/${result.job_id}`);

    } catch (error) {
      addNotification({
        type: 'error',
        header: 'Failed to process sample',
        content: error.response?.data?.error || error.message
      });
    }
  };



  const getCurrentStepText = () => {
    switch (currentStep) {
      case 1: return "Analyzing file structure";
      case 2: return "AI extracting timecard data";
      case 3: return "Validating compliance rules";
      default: return "Preparing for processing";
    }
  };

  const getStepStatus = (stepNumber) => {
    if (!uploading) return "stopped";
    if (currentStep > stepNumber) return "success";
    if (currentStep === stepNumber) return "loading";
    return "stopped";
  };

  return (
    <SpaceBetween size="l">
      <Header
        variant="h1"
        description="Upload Excel timecard files for processing through the AI pipeline"
      >
        Upload Timecard Files
      </Header>

      {/* File Upload Section */}
      <Container
        header={
          <Header variant="h2">
            Upload New File
          </Header>
        }
      >
        <SpaceBetween size="m">
          <FormField
            label="Select timecard file"
            description="Supported formats: .xlsx, .xls, .csv (max 16MB)"
          >
            <FileUpload
              onChange={({ detail }) => setFiles(detail.value)}
              value={files}
              i18nStrings={{
                uploadButtonText: e => e ? "Choose files" : "Choose file",
                dropzoneText: e => e ? "Drop files to upload" : "Drop file to upload",
                removeFileAriaLabel: e => `Remove file ${e + 1}`,
                limitShowFewer: "Show fewer files",
                limitShowMore: "Show more files",
                errorIconAriaLabel: "Error"
              }}
              showFileLastModified
              showFileSize
              showFileThumbnail
              tokenLimit={1}
              accept=".xlsx,.xls,.csv"
            />
          </FormField>



          {uploading && (
            <SpaceBetween size="s">
              <ProgressBar
                value={uploadProgress}
                label="Processing progress"
                description={`${uploadProgress}% complete - ${getCurrentStepText()}`}
              />
              {uploadProgress > 10 && (
                <Box variant="small" color="text-status-info">
                  This may take up to 30 seconds to complete
                </Box>
              )}
            </SpaceBetween>
          )}

          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="link"
                onClick={() => navigate('/jobs')}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                iconAlign="left"
                iconName="gen-ai"
                onClick={handleUpload}
                loading={uploading}
                disabled={files.length === 0}
                ariaLabel="Generative AI - Process timecard file"
              >
                Process with AI
              </Button>
            </SpaceBetween>
          </Box>
        </SpaceBetween>
      </Container>

      {/* Sample Files Section */}
      <Container
        header={
          <Header
            variant="h2"
            description="Try our AI-powered processing with pre-loaded sample timecard files"
          >
            Sample Files
          </Header>
        }
      >
        {samples.length > 0 ? (
          <Cards
            cardDefinition={{
              header: item => (
                <Box fontSize="heading-s" fontWeight="bold">
                  {item}
                </Box>
              ),
              sections: [
                {
                  id: "actions",
                  content: item => (
                    <SpaceBetween direction="horizontal" size="xs">
                      <Button
                        variant="primary"
                        size="small"
                        iconAlign="left"
                        iconName="gen-ai"
                        onClick={() => handleSampleProcess(item)}
                        ariaLabel="Generative AI - Process sample file"
                      >
                        Process with AI
                      </Button>
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
            items={samples}
            loading={loadingSamples}
            empty={
              <Box textAlign="center" color="inherit">
                <b>No sample files available</b>
                <Box variant="p" color="inherit">
                  Add sample Excel files to the data/ directory.
                </Box>
              </Box>
            }
          />
        ) : (
          <Alert type="info">
            No sample files found. Add Excel files to the data/ directory to see them here.
          </Alert>
        )}
      </Container>

      {/* Upload Guidelines */}
      <Container
        header={
          <Header variant="h2">
            Upload Guidelines
          </Header>
        }
      >
        <ColumnLayout columns={2}>
          <div>
            <Box variant="h3">Supported File Types</Box>
            <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
              <li>Excel files (.xlsx, .xls)</li>
              <li>Excel macro-enabled (.xlsm)</li>
              <li>CSV files (.csv)</li>
            </ul>
          </div>
          <div>
            <Box variant="h3">File Requirements</Box>
            <ul style={{ marginLeft: '20px', paddingLeft: '0' }}>
              <li>Maximum file size: 16MB</li>
              <li>Must contain timecard data</li>
              <li>Employee names and hours required</li>
            </ul>
          </div>
        </ColumnLayout>

        <Box variant="h3" margin={{ top: "m" }}>AI Processing Pipeline</Box>
        <ColumnLayout columns={3}>
          <div>
            <StatusIndicator type={getStepStatus(1)}>
              Step 1
            </StatusIndicator>
            <Box variant="h4">File Analysis</Box>
            <Box variant="p">
              Convert Excel data to structured markdown format for AI processing
            </Box>
            {uploading && currentStep >= 1 && (
              <Box variant="small" color="text-status-info">
                Processing...
              </Box>
            )}
          </div>
          <div>
            <StatusIndicator type={getStepStatus(2)}>
              Step 2
            </StatusIndicator>
            <Box variant="h4">AI Extraction</Box>
            <Box variant="p">
              Use Claude Sonnet to extract and validate timecard data
            </Box>
            {uploading && currentStep >= 2 && (
              <Box variant="small" color="text-status-info">
                AI analyzing data...
              </Box>
            )}
          </div>
          <div>
            <StatusIndicator type={getStepStatus(3)}>
              Step 3
            </StatusIndicator>
            <Box variant="h4">Compliance Validation</Box>
            <Box variant="p">
              Automated reasoning for federal wage compliance checking
            </Box>
            {uploading && currentStep >= 3 && (
              <Box variant="small" color="text-status-info">
                Validating compliance...
              </Box>
            )}
          </div>
        </ColumnLayout>
      </Container>
    </SpaceBetween>
  );
};

export default UploadPage;