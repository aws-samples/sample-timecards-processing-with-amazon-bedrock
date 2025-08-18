# Timecard Processing System

AWS Console-style timecard processing system with AI-powered validation and job queue management.

## 🏗️ Architecture

### Backend (Python Flask)
- **Job Queue System**: Stateless job management with file persistence
- **3-Step AI Pipeline**: Excel → Markdown → LLM Extraction → Compliance Validation
- **AWS Bedrock Integration**: Claude Sonnet 4 for intelligent data extraction
- **Federal Compliance**: Automated wage law validation with human review triggers

### Frontend (React + Cloudscape Design System)
- **AWS Console Style UI**: Professional dashboard with real-time monitoring
- **Job Management**: Upload, track, and manage processing jobs
- **Review Queue**: Human-in-the-loop validation for complex cases
- **Real-time Updates**: Live job status and progress tracking

## 🚀 Features

### Job Processing
- ✅ **Asynchronous Processing**: Upload files and track jobs in real-time
- ✅ **Priority Queue**: High/Normal/Low/Urgent priority levels
- ✅ **Progress Tracking**: Real-time progress updates with detailed status
- ✅ **Error Handling**: Comprehensive error reporting and recovery
- ✅ **File Persistence**: Stateless design survives app restarts

### AI-Powered Extraction
- ✅ **Claude Sonnet 4**: Latest AI model for accurate data extraction
- ✅ **Token Optimization**: Compact array format reduces usage by 60%
- ✅ **Daily Rate System**: Entertainment industry-compliant wage calculations
- ✅ **Multi-format Support**: Excel (.xlsx, .xls, .xlsm) and CSV files

### Compliance & Validation
- ✅ **Federal Wage Laws**: Automatic minimum wage and overtime validation
- ✅ **Human Review Queue**: Complex cases routed for manual review
- ✅ **Audit Trail**: Complete processing history and validation results
- ✅ **Risk Assessment**: Priority-based review assignment

### User Interface
- ✅ **Dashboard**: Real-time metrics, charts, and system health
- ✅ **Job Table**: Advanced filtering, sorting, and bulk operations
- ✅ **Upload Interface**: Drag-and-drop with progress tracking
- ✅ **Review Queue**: Streamlined validation workflow
- ✅ **Settings**: System configuration and maintenance tools

## 📊 Dashboard Features

### Key Metrics
- Total jobs processed
- Active processing jobs
- Completion rates
- Average processing time
- Error rates and trends

### Visualizations
- Job activity charts (24-hour view)
- Status distribution pie charts
- Processing time trends
- Queue depth monitoring

### System Health
- Queue status indicators
- Processing capacity monitoring
- Error rate alerts
- Performance metrics

## 🔄 Job Lifecycle

```
1. Upload → 2. Queue → 3. Processing → 4. Validation → 5. Complete/Review
```

### Job States
- **Pending**: Waiting in queue for processing
- **Processing**: Active AI pipeline execution
- **Completed**: Successfully processed and validated
- **Failed**: Processing error occurred
- **Cancelled**: User-cancelled before processing

### Processing Steps
1. **Excel to Markdown**: Convert spreadsheet to AI-readable format
2. **LLM Extraction**: Claude Sonnet extracts timecard data
3. **Compliance Validation**: Federal wage law compliance checking
4. **Human Review**: Complex cases routed for manual validation

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.9+
- Node.js 16+
- AWS Account with Bedrock access
- AWS CLI configured

### Backend Setup
```bash
cd backend
pip install flask flask-cors boto3 pandas openpyxl
python app.py
```

### Frontend Setup
```bash
cd frontend
npm install
npm start
```

### AWS Configuration
```bash
# Configure AWS credentials
aws configure

# Enable Bedrock models (if needed)
aws bedrock put-model-invocation-logging-configuration \
  --logging-config cloudWatchConfig='{logGroupName="/aws/bedrock/modelinvocations",roleArn="arn:aws:iam::ACCOUNT:role/service-role/AmazonBedrockExecutionRoleForKnowledgeBase_XXXXX"}'
```

## 🔧 Configuration

### Environment Variables
```bash
# Backend
export AWS_REGION=us-west-2
export FLASK_ENV=development
export PORT=8000

# Frontend
export REACT_APP_API_URL=http://localhost:8000
```

### Job Queue Settings
- **Max Concurrent Jobs**: 3 (configurable)
- **Auto Cleanup**: 7 days (configurable)
- **File Persistence**: `job_data/` directory
- **Upload Limit**: 16MB per file

## 📋 API Endpoints

### Job Management
- `POST /api/upload` - Upload file and create job
- `GET /api/jobs` - List jobs with filtering
- `GET /api/jobs/{id}` - Get job details
- `POST /api/jobs/{id}/cancel` - Cancel pending job

### Queue Operations
- `GET /api/queue/stats` - Queue statistics
- `POST /api/queue/cleanup` - Clean old jobs
- `GET /api/review-queue` - Human review items

### Sample Files
- `GET /api/samples` - List sample files
- `GET /api/process-sample/{filename}` - Process sample file

## 🎯 Usage Examples

### Upload File via UI
1. Navigate to Upload page
2. Drag and drop Excel file
3. Select priority level
4. Click "Upload and Process"
5. Track progress in Jobs table

### Process Sample File
1. Go to Upload page
2. Click "Process Sample" on any sample file
3. Monitor job in Dashboard
4. View results in Job Details

### Review Queue Workflow
1. Jobs requiring review appear in Review Queue
2. Click "Review" to examine details
3. View validation issues and timecard data
4. Approve or reject with comments

## 🔍 Monitoring & Troubleshooting

### Health Check
```bash
curl http://localhost:8000/
```

### Job Status Monitoring
- Dashboard provides real-time metrics
- Job table shows detailed status
- Progress bars for active jobs
- Error messages for failed jobs

### Log Files
- Backend: Console output with structured logging
- Job persistence: `job_data/*.json` files
- Upload files: `uploads/` directory (auto-cleanup)

## 🏢 Enterprise Features

### Compliance
- Federal minimum wage validation ($7.25/hour)
- Overtime threshold monitoring (40 hours/week)
- Salary exempt validation ($684/week)
- Excessive hours flagging (>60 hours/week)

### Audit Trail
- Complete job processing history
- Validation decision logging
- Human review tracking
- Compliance report generation

### Scalability
- Stateless job processing
- File-based persistence
- Horizontal scaling ready
- AWS cloud deployment

## 🚀 Deployment

### Local Development
```bash
# Terminal 1 - Backend
cd backend && python app.py

# Terminal 2 - Frontend
cd frontend && npm start
```

### AWS App Runner
```bash
# Build and deploy
docker build -t timecard-processor .
aws apprunner create-service --cli-input-json file://apprunner.yaml
```

### Environment Configuration
- Development: `localhost:3000` (React) + `localhost:8000` (Flask)
- Production: Single container with built React app served by Flask

## 📈 Performance

### Optimization Features
- Token-optimized LLM prompts (60% reduction)
- Compact array format for data transfer
- Real-time progress updates
- Efficient job queue management
- Background processing threads

### Scalability Metrics
- Processing: 3 concurrent jobs (configurable)
- Throughput: ~10-20 files per minute
- File size: Up to 16MB per upload
- Queue capacity: Unlimited (file-based)

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review AWS Bedrock documentation
- Verify AWS credentials and permissions

---

**Built with AWS Bedrock, Claude Sonnet 4, and Cloudscape Design System**