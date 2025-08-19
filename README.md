# Timecard Processing with Amazon Bedrock

A scalable, AI-powered timecard processing system built on Amazon Bedrock with [Automated Reasoning](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html) validation and human-in-the-loop review capabilities.

## Key Features

- **3-Step Processing Pipeline**: Excel → Markdown → LLM Extraction → Automated Reasoning Validation
- **Advanced Excel Processing**: Handles complex spreadsheet formats with enhanced parsing
- **LLM-Powered Data Extraction**: Uses Claude Sonnet 4 for intelligent timecard data extraction
- **Amazon Bedrock Automated Reasoning**: Mathematical validation using formal logic for up to 99% accuracy
- **Federal Wage Compliance**: Automated validation against federal minimum wage laws with provable assurance
- **Human-in-the-Loop**: Flags complex cases for human review with detailed reasoning
- **Real-time Processing**: Asynchronous job queue with progress tracking
- **Comprehensive Validation**: Multi-layered validation with detailed compliance reporting and formal verification

## Architecture Overview

![Architecture Diagram](preview.png)

This solution demonstrates a modern, cloud-native approach to timecard processing using AWS services including ECS Fargate, RDS PostgreSQL, Amazon Bedrock, and CloudFront. The system processes Excel/CSV timecard files through an AI pipeline that extracts data, validates compliance with federal wage laws, and routes complex cases for human review.

## Application Logic Flow

### User Journey Flow

```mermaid
graph TD
    A[User Uploads File] --> B[File Validation]
    B --> C[Job Creation]
    C --> D[Queue Processing]
    D --> E[AI Pipeline]
    E --> F[Compliance Validation]
    F --> G{Validation Result}
    G -->|Pass| H[Job Complete]
    G -->|Issues Found| I[Human Review Queue]
    I --> J[Manual Review]
    J --> K{Review Decision}
    K -->|Approve| H
    K -->|Reject| L[Job Failed]
    H --> M[Results Available]
    L --> M
```

**User Journey Explanation:**
This flow represents the complete user experience from file upload to final results. The system automatically handles file validation (checking format, size, and basic structure), creates a job with unique ID and priority level, and queues it for background processing. The AI pipeline extracts timecard data using Claude models and validates against federal wage laws. Jobs that pass validation are automatically completed, while those with compliance issues are routed to human reviewers for manual decision-making. The entire process is asynchronous, allowing users to track progress in real-time through the web interface.

### System Interaction Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as Flask API
    participant Q as Job Queue
    participant P as AI Pipeline
    participant B as Amazon Bedrock
    participant D as Database

    U->>F: Upload Excel/CSV file
    F->>A: POST /api/upload
    A->>D: Create job record
    A->>Q: Add to processing queue
    A->>F: Return job ID
    F->>U: Show job created

    loop Background Processing
        Q->>P: Get next job by priority
        P->>P: Parse Excel to structured data
        P->>B: Send to Claude AI model
        B->>P: Return extracted timecard data
        P->>P: Run compliance validation
        P->>D: Update job with results
        
        alt Validation Issues Found
            P->>D: Mark for human review
        else No Issues
            P->>D: Mark as completed
        end
    end

    loop Frontend Polling
        F->>A: GET /api/jobs (every 15s)
        A->>D: Query job status
        D->>A: Return job data
        A->>F: Job status update
        F->>U: Update UI with progress
    end
```

**System Interaction Explanation:**
This sequence diagram shows the detailed interaction between system components during timecard processing. The frontend communicates with the Flask API through RESTful endpoints, while background workers continuously poll the job queue for new tasks. The AI pipeline processes files through multiple stages: Excel parsing, data extraction via Amazon Bedrock's Claude models, and compliance validation against configurable federal wage laws. The system uses database-driven job persistence to ensure reliability across application restarts. Frontend polling occurs every 15 seconds to provide real-time status updates without overwhelming the server.

### AI Processing Pipeline

```mermaid
flowchart LR
    A[Excel/CSV File] --> B[Pandas Parser]
    B --> C[Data Normalization]
    C --> D[Markdown Conversion]
    D --> E[Claude AI Model]
    E --> F[JSON Response]
    F --> G[Data Validation]
    G --> H[Compliance Engine]
    H --> I{Validation Rules}
    I -->|Federal Min Wage| J[Wage Check: $7.25/hr]
    I -->|Overtime Rules| K[Hours Check: 40hrs/week]
    I -->|Salary Exempt| L[Exempt Check: $684/week]
    I -->|Custom Rules| M[Organization Rules]
    J --> N[Validation Results]
    K --> N
    L --> N
    M --> N
    N --> O{Issues Found?}
    O -->|No| P[Auto Approve]
    O -->|Yes| Q[Human Review Required]
```

**AI Processing Pipeline Explanation:**
The AI pipeline transforms raw timecard files into validated, structured data through a sophisticated multi-stage process. Files are first parsed using Pandas to handle various Excel/CSV formats and normalize the data structure. The normalized data is converted to markdown format optimized for AI processing, then sent to Claude AI models (configurable between Opus 4.1, Sonnet 4, or 3.7 Sonnet based on accuracy vs. cost requirements). Claude extracts structured timecard information including employee names, daily rates, hours worked, and calculates totals. The compliance engine then validates this data against federal wage laws: minimum wage compliance ($7.25/hour default), overtime calculations (40+ hours/week), salary exempt thresholds ($684/week), and any custom organizational rules. Jobs with validation issues are automatically flagged for human review, while compliant timecards are approved for immediate processing.

### Key Components

- **Frontend**: React application with AWS Cloudscape Design System
- **Backend**: Python Flask API with asynchronous job processing
- **Database**: PostgreSQL (AWS RDS) for production, SQLite for local development
- **AI Processing**: Amazon Bedrock with Claude models for intelligent data extraction
- **Infrastructure**: Fully automated deployment using Terraform
- **Monitoring**: CloudWatch Logs with structured logging and health checks

## Core Application Logic

### Job Processing Architecture

The system implements a robust, asynchronous job processing architecture designed for high throughput and reliability:

#### Job Lifecycle Management
**Job Creation Process:**
When a user uploads a timecard file, the system immediately creates a job record in the database with a unique UUID, assigns priority based on user selection (Urgent=4, High=3, Normal=2, Low=1), and stores the file in S3 with secure access controls. The job starts in "pending" status and enters the priority-based processing queue.

**Queue Processing Logic:**
A background worker continuously polls the database for pending jobs using `ORDER BY priority DESC, created_at ASC` to ensure high-priority jobs are processed first, with FIFO ordering within the same priority level. The system supports 1-10 concurrent workers (configurable via settings), with each worker acquiring jobs atomically to prevent race conditions.

**State Transitions:**
Jobs progress through defined states: Pending → Processing → (Completed|Failed|Review). The system updates job status, progress percentage, and timestamps at each stage, enabling real-time progress tracking in the frontend.

#### AI Processing Pipeline

**Data Extraction Stage:**
The system uses Pandas to parse Excel/CSV files into normalized DataFrames, handling various formats (.xlsx, .xls, .xlsm, .csv) and encoding issues. Data is then converted to a structured markdown format optimized for AI processing, including employee information, daily rates, hours worked, and date ranges.

**AI Model Integration:**
The system integrates with Amazon Bedrock's Claude models through configurable model selection:
- **Claude Opus 4.1**: Highest accuracy for complex timecards, slower processing
- **Claude Sonnet 4**: Balanced performance for general use cases  
- **Claude 3.7 Sonnet**: Fastest processing for simple timecards, cost-optimized

The AI prompt is optimized to extract structured JSON data including employee names, daily rates, total days worked, and calculated wages, with built-in validation for data consistency.

**Compliance Validation Engine:**
Post-AI processing, the system runs extracted data through a configurable compliance engine that validates:
- **Federal Minimum Wage**: Ensures daily rates meet or exceed $7.25/hour equivalent
- **Overtime Rules**: Flags weeks exceeding 40 hours for overtime calculation review
- **Salary Exempt Thresholds**: Validates weekly salaries above $684 for exempt status
- **Custom Organizational Rules**: Supports additional validation parameters

#### Human Review Workflow

**Automatic Review Routing:**
Jobs are automatically flagged for human review when:
- Compliance validation fails (wage law violations)
- AI extraction confidence is below threshold
- Data inconsistencies are detected (missing dates, negative values)
- Custom business rules trigger review requirements

**Review Queue Management:**
The review queue presents flagged jobs with detailed validation issues, extracted data preview, and calculated wage information. Human reviewers can approve jobs (marking them as completed) or reject them (marking as failed) with optional comments for audit trails.

**Audit and Compliance Tracking:**
All review decisions are logged with timestamps, reviewer actions, and reasoning for compliance reporting and audit purposes.

#### Database Design and Performance

**Multi-Database Compatibility:**
The system supports both PostgreSQL (production) and SQLite (development) through a unified database abstraction layer. Connection strings are automatically detected via environment variables, enabling seamless deployment across environments.

**Query Optimization:**
Database queries are optimized for performance with proper indexing on frequently queried fields (status, created_at, priority). The system uses connection pooling and prepared statements to minimize database overhead.

**Data Persistence Strategy:**
Job data, including processing results and validation outcomes, is stored as JSONB in PostgreSQL for flexible querying, while maintaining structured fields for performance-critical operations like status filtering and priority sorting.

#### Error Handling and Resilience

**Retry Mechanisms:**
The system implements exponential backoff retry logic for transient failures, including database connection issues, S3 access problems, and AI service timeouts. Failed jobs are automatically retried up to 3 times before being marked as failed.

**Circuit Breaker Pattern:**
AI service calls are protected by circuit breaker logic that temporarily disables processing when Amazon Bedrock experiences outages, preventing cascade failures and resource exhaustion.

**Graceful Degradation:**
When AI services are unavailable, the system can optionally route jobs directly to human review queues, ensuring business continuity during service disruptions.

## Features

### Core Functionality

- **Asynchronous Processing**: Upload files and track jobs in real-time with priority queuing
- **AI-Powered Extraction**: Multiple Claude model support (Opus 4.1, Sonnet 4, 3.7 Sonnet)
- **Compliance Validation**: Configurable federal wage law validation with custom parameters
- **Human Review Queue**: Complex cases routed for manual validation with audit trail
- **Multi-format Support**: Excel (.xlsx, .xls, .xlsm) and CSV file processing

### Enterprise Features

- **High Availability**: Multi-AZ deployment with auto-scaling
- **Security**: VPC isolation, IAM roles, encrypted storage
- **Monitoring**: Real-time metrics, health checks, and operational insights
- **Scalability**: Horizontal scaling with ECS Fargate and RDS
- **Cost Optimization**: Automated cleanup policies and resource optimization

## Prerequisites

### Local Development

- Python 3.9+
- Node.js 16+
- Docker
- AWS CLI configured with appropriate permissions

### AWS Deployment

- AWS Account with Bedrock access enabled
- Terraform 1.0+
- Domain registered in Route 53 (optional)
- ACM certificate (automatically provisioned if domain provided)
- Amazon Bedrock Automated Reasoning access (preview/GA regions)

## Quick Start

### Local Development

```bash
# Clone the repository
git clone https://github.com/aws-samples/sample-timecards-processing-with-amazon-bedrock
cd sample-timecards-processing-with-amazon-bedrock

# Backend setup
cd backend
pip install -r requirements.txt
python app.py  # Automated Reasoning setup starts in background

# Frontend setup (new terminal)
cd frontend
npm install
npm start
```

Access the application at `http://localhost:3000`

### AWS Deployment

```bash
# Navigate to terraform directory
cd terraform

# Configure deployment variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your configuration

# Deploy infrastructure
terraform init
terraform plan
terraform apply

# Automated Reasoning setup runs automatically when app starts
# Check status: cd ../backend && python check_ar_status.py
```

The deployment process automatically:
1. Creates VPC, subnets, and security groups
2. Provisions RDS PostgreSQL database
3. Sets up ECS Fargate cluster with auto-scaling
4. Builds and pushes Docker images to ECR
5. Deploys React application to S3 and CloudFront
6. Configures Route 53 DNS and ACM certificates

## Configuration

### Environment Variables

#### Production (AWS)
- `DATABASE_URL`: PostgreSQL connection string (automatically configured)
- `AWS_DEFAULT_REGION`: AWS region for services
- `S3_BUCKET`: S3 bucket for file uploads
- `FLASK_ENV`: Set to "production"
- `AUTOMATED_REASONING_POLICY_ARN`: ARN of the Automated Reasoning policy
- `AUTOMATED_REASONING_GUARDRAIL_ID`: ID of the Automated Reasoning guardrail
- `AUTOMATED_REASONING_GUARDRAIL_VERSION`: Version of the guardrail (default: DRAFT)

#### Development (Local)
- No `DATABASE_URL`: Automatically uses SQLite
- `AWS_REGION`: For Bedrock API calls
- `FLASK_ENV`: Set to "development"
- `AUTOMATED_REASONING_POLICY_ARN`: ARN of the Automated Reasoning policy (optional)
- `AUTOMATED_REASONING_GUARDRAIL_ID`: ID of the Automated Reasoning guardrail (optional)

### Terraform Variables

Key configuration options in `terraform.tfvars`:

```hcl
# Project Configuration
project_name = "timecard-processor"
environment  = "prod"
aws_region   = "us-west-2"

# Custom Domain (optional)
domain_name = "timecard.yourdomain.com"

# Database Configuration
db_instance_class = "db.t4g.micro"
db_multi_az       = false

# ECS Configuration
ecs_task_cpu      = 512
ecs_task_memory   = 1024
ecs_desired_count = 2
ecs_min_capacity  = 1
ecs_max_capacity  = 10

# Auto Scaling
enable_auto_scaling = true
```

### Automated Reasoning Setup

The system uses Amazon Bedrock Automated Reasoning for mathematical validation of timecard data. This provides up to 99% accuracy in detecting calculation errors and data inconsistencies using formal logic.

#### Automatic Setup Flow

The system automatically provisions Automated Reasoning resources **asynchronously** when first started:

```bash
cd backend
python app.py  # Non-blocking auto-provisioning starts
```

**Setup Flow:**
```
1. App Start
   ↓
2. Check Status (not_configured) → Start Creation
   ↓
3. Create Policy (quick) → Status: creating
   ↓
4. Start Build Workflow → Background Processing
   ↓
5. App Ready (no blocking) → Users can upload files
   ↓
6. Build Completes → Create Guardrail → Status: ready
   ↓
7. Full Automated Reasoning Active
```

**Status Monitoring:**
```bash
# Check current status
python check_ar_status.py

# Via API
curl http://localhost:5000/api/automated-reasoning/status
```

**What happens automatically:**
- **Non-blocking**: App starts immediately, setup runs in background
- **State tracking**: Progress saved in database
- **Duplicate prevention**: Reuses existing policies
- **Graceful fallback**: Basic validation until Automated Reasoning ready
- **Progress monitoring**: Check status via API or script

#### Status States

- **`not_configured`**: Initial state, setup will start on first run
- **`creating`**: Policy created, build workflow in progress
- **`ready`**: Fully configured and active
- **`failed`**: Setup failed, check logs and retry

#### Troubleshooting

```bash
# Check detailed status
cd backend
python check_ar_status.py

# Retry setup if failed
curl -X POST http://localhost:5000/api/automated-reasoning/retry

# Debug step-by-step
python debug_provisioning.py
```

#### Mathematical Validation

The system validates:
- **Sum accuracy**: Total wage = sum of daily rates
- **Count consistency**: Employee count matches unique employees
- **Calculation correctness**: Average = total ÷ count
- **Data integrity**: No negative values or missing fields

## Usage Examples

### Basic Timecard Processing

```python
from timecard_pipeline import TimecardPipeline
from config_manager import ConfigManager
from database import DatabaseManager

# Initialize pipeline
db_manager = DatabaseManager()
config_manager = ConfigManager(db_manager)
pipeline = TimecardPipeline(config_manager)

# Process timecard file
result = pipeline.process("sample_timecard.xlsx")

if result["status"] == "success":
    validation = result["validation"]
    print(f"Employee: {validation['employee_name']}")
    print(f"Total Wage: ${validation['total_wage']:.2f}")
    print(f"Validation: {validation['validation_result']}")
    
    if validation["requires_human_review"]:
        print("WARNING: Requires human review")
        for issue in validation["validation_issues"]:
            print(f"  - {issue}")
```

### Automated Reasoning Validation Results

The system applies Automated Reasoning during LLM extraction and returns detailed validation results:

```json
{
  "validation_result": "INVALID",
  "employee_name": "Jane Smith",
  "total_wage": 800.00,
  "average_daily_rate": 400.00,
  "validation_issues": [
    "Sum calculation error: Total wage (800.00) ≠ Sum of daily rates (700.00)",
    "Average calculation error: Reported (400.00) ≠ Calculated (350.00)"
  ],
  "mathematical_consistency": false,
  "automated_reasoning_applied": true,
  "extraction_method": "tool_use_with_guardrail",
  "model_info": {
    "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "guardrail_applied": true
  },
  "validation_method": "automated_reasoning",
  "validation_findings": [
    {
      "result": "INVALID",
      "ruleId": "sum_validation_check",
      "ruleDescription": "Total wage must equal sum of all daily rates",
      "variables": {
        "reported_total_wage": 800.00,
        "calculated_sum": 700.00
      },
      "suggestions": ["Correct total wage to 700.00"]
    }
  ],
  "mathematical_validation": {
    "sum_correct": false,
    "average_correct": false,
    "count_correct": true,
    "data_integrity": true
  }
}
```

### Mathematical Validation Example

Test mathematical consistency of timecard data:

```python
from automated_reasoning_utils import run_valid_at_n_experiment

# Test data with calculation error
user_query = "Validate timecard: 3 days, rates [200, 250, 300], total wage: 800"
initial_response = "Total wage 800 is correct for 3 days of work"

# Run experiment to see how many iterations needed to fix the error
results = run_valid_at_n_experiment(
    user_query=user_query,
    initial_response=initial_response,
    policy_definition=policy_def,
    guardrail_id="your-guardrail-id",
    guardrail_version="DRAFT",
    runtime_client=bedrock_runtime
)

print(f"Valid at N = {results['n_value']}")
print(f"Final corrected response: {results['final_valid_response']}")
# Expected: "Total wage should be 750 (200+250+300), not 800"
```

### Testing Mathematical Validation

Run comprehensive tests for mathematical validation:

```bash
cd backend
python test_automated_reasoning.py
```

This tests various scenarios:
- Correct calculations and counts
- Sum calculation errors  
- Count mismatches
- Negative values
- Missing data fields

## API Reference

### Job Management Endpoints

#### Upload and Job Creation
```http
POST /api/upload
Content-Type: multipart/form-data

Parameters:
- file: Excel/CSV file (required, max 16MB)
- priority: Job priority (optional, default: "normal")
  - Values: "low", "normal", "high", "urgent"

Response:
{
  "job_id": "uuid-string",
  "status": "pending",
  "message": "Job created successfully"
}
```

#### Job Status and Management
```http
GET /api/jobs?limit=50&status=completed,pending
Response:
{
  "jobs": [
    {
      "id": "job-uuid",
      "type": "timecard_processing",
      "status": "completed|pending|processing|failed|cancelled",
      "priority": 1-4,
      "file_name": "timecard.xlsx",
      "file_size": 1024000,
      "progress": 100,
      "created_at": "2025-08-18T05:00:00Z",
      "completed_at": "2025-08-18T05:05:00Z",
      "result": {
        "extracted_data": {...},
        "validation": {...}
      }
    }
  ],
  "total": 25
}
```

#### Job Details
```http
GET /api/jobs/{job_id}
Response:
{
  "job": {
    "id": "job-uuid",
    "status": "completed",
    "result": {
      "extracted_data": {
        "employee_name": "John Doe",
        "total_days": 5,
        "daily_rates": [500, 500, 500, 500, 500],
        "unique_days": 5
      },
      "validation": {
        "validation_result": "PASS",
        "total_wage": 2500.00,
        "average_daily_rate": 500.00,
        "requires_human_review": false,
        "validation_issues": []
      }
    }
  }
}
```

### Queue Operations

#### Queue Statistics
```http
GET /api/queue/stats
Response:
{
  "pending": 5,
  "processing": 2,
  "completed": 150,
  "failed": 3,
  "cancelled": 1,
  "review_queue": 8,
  "total_jobs": 169,
  "avg_processing_time": 45,
  "success_rate": 96.2,
  "jobs_today": 25
}
```

#### Human Review Queue
```http
GET /api/review-queue
Response:
{
  "review_queue": [
    {
      "id": "review_job-uuid",
      "job_id": "job-uuid",
      "file_name": "timecard.xlsx",
      "employee_name": "Jane Smith",
      "validation_result": "REQUIRES_HUMAN_REVIEW",
      "validation_issues": [
        "Daily rate below federal minimum wage",
        "Excessive hours detected (65 hours/week)"
      ],
      "total_wage": 1800.00,
      "average_daily_rate": 300.00,
      "total_days": 6,
      "created_at": "2025-08-18T04:30:00Z",
      "status": "pending"
    }
  ],
  "count": 8
}
```

### Settings Management

#### Compliance Configuration
```http
GET /api/settings
Response:
{
  "federal_minimum_wage": 7.25,
  "overtime_threshold_hours": 40,
  "salary_exempt_threshold": 684,
  "max_recommended_hours": 60,
  "claude_model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
  "aws_region": "us-west-2",
  "max_concurrent_jobs": 3,
  "auto_cleanup_days": 7
}
```

#### Update Settings
```http
POST /api/settings
Content-Type: application/json

{
  "federal_minimum_wage": 8.00,
  "claude_model": "anthropic.claude-opus-4-1-20250805-v1:0"
}

Response:
{
  "message": "Settings updated successfully",
  "updated_settings": ["federal_minimum_wage", "claude_model"]
}
```

### Automated Reasoning Management

#### Get Automated Reasoning Status
```http
GET /api/automated-reasoning/status
Response:
{
  "status": "ready",
  "policy_arn": "arn:aws:bedrock:us-west-2:123456789012:automated-reasoning-policy/abc123",
  "guardrail_id": "guardrail-xyz789",
  "guardrail_version": "DRAFT",
  "message": "Automated Reasoning setup completed successfully!",
  "build_status": null,
  "created": true,
  "error": null,
  "last_check": 1642781234.567,
  "created_at": 1642780000.123
}
```

#### Retry Automated Reasoning Setup
```http
POST /api/automated-reasoning/retry
Response:
{
  "status": "success",
  "message": "Automated Reasoning setup retry initiated",
  "result": {
    "status": "creating",
    "policy_arn": "arn:aws:bedrock:us-west-2:123456789012:automated-reasoning-policy/new123"
  }
}
```

### Health and Monitoring

#### Health Check
```http
GET /health
Response:
{
  "status": "healthy",
  "service": "timecard-processor",
  "database": "postgresql",
  "queue_stats": {
    "pending": 2,
    "processing": 1,
    "total_jobs": 156
  }
}
```

### Error Responses

All endpoints return consistent error responses:

```http
HTTP 400 Bad Request
{
  "error": "Invalid file format",
  "message": "Only Excel and CSV files are supported",
  "code": "INVALID_FILE_FORMAT"
}

HTTP 404 Not Found
{
  "error": "Job not found",
  "message": "Job with ID 'invalid-uuid' does not exist",
  "code": "JOB_NOT_FOUND"
}

HTTP 500 Internal Server Error
{
  "error": "Processing failed",
  "message": "AI service temporarily unavailable",
  "code": "AI_SERVICE_ERROR"
}
```

## Database Schema

### Jobs Table

| Column       | Type         | Description                            |
| ------------ | ------------ | -------------------------------------- |
| id           | VARCHAR(36)  | Unique job identifier                  |
| type         | VARCHAR(100) | Job type (e.g., "timecard_processing") |
| status       | VARCHAR(20)  | Current job status                     |
| priority     | INTEGER      | Job priority (1-4)                     |
| file_name    | VARCHAR(255) | Original filename                      |
| file_size    | BIGINT       | File size in bytes                     |
| created_at   | TIMESTAMP    | Job creation time                      |
| updated_at   | TIMESTAMP    | Last update time                       |
| started_at   | TIMESTAMP    | Processing start time                  |
| completed_at | TIMESTAMP    | Processing completion time             |
| progress     | INTEGER      | Progress percentage (0-100)            |
| result       | JSONB        | Processing results                     |
| error        | TEXT         | Error message if failed                |
| metadata     | JSONB        | Additional job metadata                |

### Settings Table

| Column     | Type         | Description      |
| ---------- | ------------ | ---------------- |
| key        | VARCHAR(100) | Setting key      |
| value      | JSONB        | Setting value    |
| updated_at | TIMESTAMP    | Last update time |

## Monitoring and Observability

### CloudWatch Metrics

- ECS service metrics (CPU, memory utilization)
- Application Load Balancer metrics (request count, response time)
- RDS metrics (connections, CPU, storage)
- Custom application metrics via CloudWatch Logs

### Health Checks

- ECS container health checks with configurable parameters
- ALB target group health checks on `/health` endpoint
- Database connection validation in health check response

### Logging

Structured logging with the following log levels:
- `INFO`: Normal operations and job status changes
- `WARNING`: Recoverable errors and retry attempts
- `ERROR`: Unrecoverable errors requiring attention
- `DEBUG`: Detailed debugging information (development only)

## Security Considerations

### Network Security

- VPC with private subnets for application and database tiers
- Security groups with least-privilege access rules
- NAT Gateways for outbound internet access from private subnets
- Application Load Balancer in public subnets only

### Data Protection

- Encryption at rest for RDS and S3
- Encryption in transit with HTTPS/TLS
- IAM roles with minimal required permissions
- S3 bucket policies preventing public access

### Access Control

- ECS tasks run with dedicated IAM roles
- Bedrock access limited to specific model ARNs
- Database credentials managed via environment variables
- CloudFront Origin Access Control for S3 protection

## Cost Optimization

### Resource Optimization

- ECS Fargate with right-sized CPU/memory allocation
- RDS instance class selection based on workload
- S3 lifecycle policies for automatic cleanup
- CloudFront caching to reduce origin requests

### Monitoring and Alerts

- CloudWatch billing alerts for cost monitoring
- Resource utilization metrics for optimization opportunities
- Automated cleanup of old jobs and uploaded files

## Troubleshooting

### Common Issues

#### ECS Task Startup Failures

```bash
# Check ECS service events
aws ecs describe-services --cluster timecard-processor-cluster --services timecard-processor-service

# View container logs
aws logs tail /ecs/timecard-processor --follow
```

#### Database Connection Issues

```bash
# Test database connectivity from ECS task
aws ecs execute-command --cluster timecard-processor-cluster --task <task-id> --interactive --command "/bin/bash"

# Inside container
curl http://localhost:8080/health
```

#### Bedrock Permission Errors

Verify IAM role has required Bedrock permissions:
- `bedrock:InvokeModel`
- `bedrock:InvokeModelWithResponseStream`
- `bedrock:ListFoundationModels`

### Log Analysis

```bash
# Filter logs by error level
aws logs filter-log-events --log-group-name /ecs/timecard-processor --filter-pattern "ERROR"

# Monitor real-time logs
aws logs tail /ecs/timecard-processor --follow --filter-pattern "{ $.level = \"ERROR\" }"
```

## Development

### Local Development Setup

1. **Database**: Uses SQLite automatically when `DATABASE_URL` is not set
2. **AWS Services**: Configure AWS CLI with development credentials
3. **Frontend**: React development server with hot reload
4. **Backend**: Flask development server with auto-reload

### Testing

```bash
# Backend tests
cd backend
python -m pytest tests/

# Frontend tests
cd frontend
npm test

# Integration tests
npm run test:integration
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit changes (`git commit -am 'Add new feature'`)
4. Push to branch (`git push origin feature/new-feature`)
5. Create Pull Request

## Deployment Pipeline

### Automated Deployment

The Terraform configuration includes automated deployment triggers:

- **Code Changes**: Detects changes in backend Python files, frontend React files, and Dockerfile
- **Docker Build**: Automatically builds and pushes new images to ECR
- **ECS Update**: Forces new deployment with updated container images
- **Frontend Deploy**: Builds React app and uploads to S3 with CloudFront invalidation

### Manual Deployment

```bash
# Force rebuild and redeploy
terraform apply -replace="null_resource.docker_build_push"

# Update only frontend
terraform apply -target="null_resource.upload_frontend"

# Update only ECS service
terraform apply -target="null_resource.ecs_service_update"
```

## License

This project is licensed under the MIT License. See the [LICENSE](https://github.com/aws-samples/sample-timecards-processing-with-amazon-bedrock/blob/main/LICENSE) file for details.

## Support

For questions, issues, or contributions:

1. Check existing [Issues](https://github.com/aws-samples/sample-timecards-processing-with-amazon-bedrock/issues)
2. Create a new issue with detailed description

## Security

See [CONTRIBUTING](https://github.com/aws-samples/sample-timecards-processing-with-amazon-bedrock/blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## Additional Resources

- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [ECS Fargate Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [React Cloudscape Design System](https://cloudscape.design/)

---

**Note**: This is a sample application for demonstration purposes. Review and modify security settings, resource configurations, and access policies according to your organization's requirements before deploying to production environments.