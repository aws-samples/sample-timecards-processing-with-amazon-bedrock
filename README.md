# Timecard Processing System

A scalable, AI-powered timecard processing system built on AWS with automated compliance validation and human-in-the-loop review capabilities.

## Architecture Overview

This solution demonstrates a modern, cloud-native approach to timecard processing using AWS services including ECS Fargate, RDS PostgreSQL, AWS Bedrock, and CloudFront. The system processes Excel/CSV timecard files through an AI pipeline that extracts data, validates compliance with federal wage laws, and routes complex cases for human review.

### Key Components

- **Frontend**: React application with AWS Cloudscape Design System
- **Backend**: Python Flask API with asynchronous job processing
- **Database**: PostgreSQL (AWS RDS) for production, SQLite for local development
- **AI Processing**: AWS Bedrock with Claude models for intelligent data extraction
- **Infrastructure**: Fully automated deployment using Terraform
- **Monitoring**: CloudWatch Logs with structured logging and health checks

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

## Quick Start

### Local Development

```bash
# Clone the repository
git clone <repository-url>
cd timecard-processing-system

# Backend setup
cd backend
pip install -r requirements.txt
python app.py

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

#### Development (Local)
- No `DATABASE_URL`: Automatically uses SQLite
- `AWS_REGION`: For Bedrock API calls
- `FLASK_ENV`: Set to "development"

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

## API Reference

### Job Management

- `POST /api/upload` - Upload file and create processing job
- `GET /api/jobs` - List jobs with optional filtering
- `GET /api/jobs/{id}` - Get job details and status
- `POST /api/jobs/{id}/cancel` - Cancel pending job
- `DELETE /api/jobs/{id}` - Delete completed job

### Queue Operations

- `GET /api/queue/stats` - Get queue statistics and metrics
- `POST /api/queue/cleanup` - Clean up old completed jobs
- `GET /api/review-queue` - Get items requiring human review

### Settings Management

- `GET /api/settings` - Get all system settings
- `POST /api/settings` - Update multiple settings
- `GET /api/settings/{key}` - Get specific setting value
- `PUT /api/settings/{key}` - Update specific setting

### Health and Monitoring

- `GET /health` - Health check endpoint for load balancers
- `GET /` - Service status with queue statistics

## Database Schema

### Jobs Table

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR(36) | Unique job identifier |
| type | VARCHAR(100) | Job type (e.g., "timecard_processing") |
| status | VARCHAR(20) | Current job status |
| priority | INTEGER | Job priority (1-4) |
| file_name | VARCHAR(255) | Original filename |
| file_size | BIGINT | File size in bytes |
| created_at | TIMESTAMP | Job creation time |
| updated_at | TIMESTAMP | Last update time |
| started_at | TIMESTAMP | Processing start time |
| completed_at | TIMESTAMP | Processing completion time |
| progress | INTEGER | Progress percentage (0-100) |
| result | JSONB | Processing results |
| error | TEXT | Error message if failed |
| metadata | JSONB | Additional job metadata |

### Settings Table

| Column | Type | Description |
|--------|------|-------------|
| key | VARCHAR(100) | Setting key |
| value | JSONB | Setting value |
| updated_at | TIMESTAMP | Last update time |

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

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Support

For questions, issues, or contributions:

1. Check existing [Issues](../../issues)
2. Create a new issue with detailed description
3. For security issues, please email [security@example.com](mailto:security@example.com)

## Additional Resources

- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [ECS Fargate Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [React Cloudscape Design System](https://cloudscape.design/)

---

**Note**: This is a sample application for demonstration purposes. Review and modify security settings, resource configurations, and access policies according to your organization's requirements before deploying to production environments.