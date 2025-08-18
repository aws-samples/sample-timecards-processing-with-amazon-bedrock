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
- ✅ **Multiple Claude Models**: Support for Claude Opus 4.1, Sonnet 4, and 3.7 Sonnet
- ✅ **Configurable Model Selection**: Choose AI model based on complexity and cost requirements
- ✅ **Token Optimization**: Compact array format reduces usage by 60%
- ✅ **Daily Rate System**: Entertainment industry-compliant wage calculations
- ✅ **Multi-format Support**: Excel (.xlsx, .xls, .xlsm) and CSV files

### Compliance & Validation
- ✅ **Configurable Compliance Rules**: Editable federal wage laws and thresholds
- ✅ **Dynamic Validation**: Real-time compliance checking with custom parameters
- ✅ **Human Review Queue**: Complex cases routed for manual review
- ✅ **Audit Trail**: Complete processing history and validation results
- ✅ **Risk Assessment**: Priority-based review assignment

### User Interface
- ✅ **Dashboard**: Real-time metrics, charts, and system health
- ✅ **Job Table**: Advanced filtering, sorting, and bulk operations
- ✅ **Upload Interface**: Drag-and-drop with progress tracking
- ✅ **Review Queue**: Streamlined validation workflow
- ✅ **Advanced Settings**: Configurable compliance rules, model selection, and system parameters
- ✅ **System Information**: Real-time platform detection and browser information

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
export CLAUDE_MODEL=anthropic.claude-sonnet-4-20250514-v1:0
export FLASK_ENV=development
export PORT=8000

# Frontend
export REACT_APP_API_URL=http://localhost:8000
```

### Configurable Settings (via UI)

#### Job Processing
- **Max Concurrent Jobs**: 1-10 jobs (default: 3)
- **Auto Cleanup**: 1-30 days (default: 7)
- **Notifications**: Enable/disable job status notifications

#### AWS Configuration
- **Region Selection**: US East 1, US West 2, EU West 1, AP Southeast 1
- **Claude Model**: Choose from Opus 4.1, Sonnet 4, or 3.7 Sonnet
- **Credentials**: Environment variables or IAM roles

#### Compliance Rules (Editable)
- **Federal Minimum Wage**: $7.25/hour (configurable)
- **Overtime Threshold**: 40 hours/week (configurable)
- **Salary Exempt Threshold**: $684/week (configurable)
- **Max Recommended Hours**: 60 hours/week (configurable)

### File Storage
- **Upload Directory**: `uploads/` (auto-cleanup)
- **Database**: SQLite with settings persistence
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

### Settings Management
- `GET /api/settings` - Get all system settings
- `POST /api/settings` - Update multiple settings
- `GET /api/settings/{key}` - Get specific setting
- `PUT /api/settings/{key}` - Update specific setting

### Sample Files
- `GET /api/samples` - List sample files
- `GET /api/process-sample/{filename}` - Process sample file

## ⚙️ Advanced Configuration

### Claude Model Selection
Choose the optimal AI model based on your needs:

| Model | Use Case | Speed | Accuracy | Cost |
|-------|----------|-------|----------|------|
| **Claude Opus 4.1** | Complex timecards, high accuracy required | Slow | Highest | High |
| **Claude Sonnet 4** | General purpose, balanced performance | Medium | High | Medium |
| **Claude 3.7 Sonnet** | Simple timecards, cost optimization | Fast | Good | Low |

### Compliance Rule Customization
Adapt the system to your organization's requirements:

- **Minimum Wage**: Set custom rates above federal minimum
- **Overtime Rules**: Configure weekly hour thresholds
- **Salary Thresholds**: Adjust exempt employee limits
- **Review Triggers**: Set custom flagging criteria

### System Monitoring
Built-in monitoring and health checks:

- **Platform Detection**: Automatic Mac ARM/Intel detection
- **Browser Compatibility**: Real-time browser information
- **AWS Status**: Credential and service validation
- **Model Availability**: Bedrock model access verification

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

### Settings Configuration
1. Navigate to Settings page
2. Configure compliance rules (wages, thresholds)
3. Select preferred Claude model
4. Set AWS region and processing limits
5. Enable/disable auto-cleanup and notifications
6. Save settings (persisted in database)

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

### Compliance (Configurable)
- **Federal minimum wage validation**: Configurable rate (default: $7.25/hour)
- **Overtime threshold monitoring**: Configurable hours (default: 40 hours/week)
- **Salary exempt validation**: Configurable threshold (default: $684/week)
- **Excessive hours flagging**: Configurable limit (default: 60 hours/week)
- **Real-time rule updates**: Changes apply immediately to new jobs

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
- **Token-optimized LLM prompts**: 60% reduction in API costs
- **Compact array format**: Efficient data transfer
- **Real-time progress updates**: WebSocket-like responsiveness
- **Efficient job queue management**: SQLite-based persistence
- **Background processing threads**: Non-blocking operations

### Model Performance Comparison
- **Claude Opus 4.1**: Highest accuracy, slower processing, higher cost
- **Claude Sonnet 4**: Balanced performance, recommended for most use cases
- **Claude 3.7 Sonnet**: Faster processing, lower cost, good for simple timecards

### Scalability Metrics
- **Processing**: 1-10 concurrent jobs (configurable via UI)
- **Throughput**: ~10-20 files per minute (model-dependent)
- **File size**: Up to 16MB per upload
- **Queue capacity**: Unlimited (database-based)
- **Settings persistence**: Real-time configuration updates

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

## 🔄 Recent Updates

### Version 1.1.0 (Latest)
- ✅ **Multi-Model Support**: Claude Opus 4.1, Sonnet 4, and 3.7 Sonnet
- ✅ **Configurable Compliance**: Editable wage laws and validation rules
- ✅ **Enhanced Settings UI**: Real-time configuration with database persistence
- ✅ **System Information**: Platform detection and browser compatibility
- ✅ **Improved Validation**: Dynamic compliance checking with custom parameters

### Version 1.0.0
- ✅ **Core Pipeline**: Excel → Markdown → LLM → Validation
- ✅ **Job Queue System**: Asynchronous processing with progress tracking
- ✅ **AWS Integration**: Bedrock and Claude Sonnet integration
- ✅ **Review Queue**: Human-in-the-loop validation workflow
- ✅ **Dashboard UI**: Real-time monitoring and management

## 🛠️ Technology Stack

### Backend
- **Python 3.9+** with Flask web framework
- **AWS Bedrock** for AI model access
- **SQLite** for job queue and settings persistence
- **Pandas** for Excel/CSV processing
- **Boto3** for AWS service integration

### Frontend
- **React 18** with modern hooks and context
- **Cloudscape Design System** for AWS Console-style UI
- **Real-time Updates** via polling and state management
- **Responsive Design** for desktop and mobile

### AI Models
- **Claude Opus 4.1**: `anthropic.claude-opus-4-1-20250805-v1:0`
- **Claude Sonnet 4**: `anthropic.claude-sonnet-4-20250514-v1:0`
- **Claude 3.7 Sonnet**: `anthropic.claude-3-7-sonnet-20250219-v1:0`

---

**Built with AWS Bedrock, Multiple Claude Models, and Cloudscape Design System**