# Cast & Crew Timecard Processing System

Automated Excel timecard processing pipeline with AI extraction and validation using Claude Sonnet 4 with thinking capabilities.

## 🎭 Design Philosophy

### Entertainment Industry Focus
This system is purpose-built for the entertainment industry's unique payroll requirements:
- **Daily Rate System**: Reflects Hollywood's standard daily compensation model
- **Federal Compliance**: Automated wage law validation for complex entertainment contracts
- **Flexible Formats**: Handles diverse Excel templates from different productions
- **Human-in-Loop**: Critical decisions routed to HR professionals

### Technical Principles
- **AI-First Processing**: Claude Sonnet 4 with thinking capabilities for complex data extraction
- **Token Optimization**: 60% token reduction through compact array formats
- **Dual Validation**: Backend AI + Frontend verification for data integrity
- **Production Ready**: Single container deployment with auto-scaling

## 🏗️ Application Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Cast & Crew Timecard Processor               │
├─────────────────────────────────────────────────────────────────┤
│  Frontend (React 18)                                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   File Upload   │  │   Pagination    │  │  MD Rendering   │ │
│  │   Drag & Drop   │  │   Sticky UI     │  │  Raw/Rendered   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Data Validation │  │ Currency Format │  │ Real-time Calc  │ │
│  │ Frontend Verify │  │ Professional $  │  │ Independent Sum │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Backend (Flask + Claude Sonnet 4)                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Excel→Markdown  │  │  AI Extraction  │  │   Validation    │ │
│  │ Table Detection │  │ Thinking Budget │  │ Federal Comply  │ │
│  │ Auto Headers    │  │ Token Optimized │  │ Business Rules  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

Data Flow:
Excel File → Markdown → Claude Analysis → Validation → React Display
     ↓            ↓           ↓              ↓            ↓
  Uploads/    Structured   AI Thinking   Compliance   User Interface
  Samples     Tables       2000 tokens   Checking     + Verification
```

## ☁️ AWS Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Cloud Infrastructure                 │
├─────────────────────────────────────────────────────────────────┤
│  Internet Gateway                                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    App Runner Service                       │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │ │
│  │  │   Auto Scaling  │  │  Load Balancer  │  │ Health Check│ │ │
│  │  │   1-10 vCPU     │  │   Built-in      │  │  /health    │ │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────┘ │ │
│  │  ┌─────────────────────────────────────────────────────────┐ │ │
│  │  │              Container Runtime                          │ │ │
│  │  │  ┌─────────────────┐  ┌─────────────────────────────────┐│ │ │
│  │  │  │   React Build   │  │         Flask Backend           ││ │ │
│  │  │  │   Static Files  │  │    ┌─────────────────────────┐  ││ │ │
│  │  │  │   Port 8080     │  │    │   Timecard Pipeline     │  ││ │ │
│  │  │  └─────────────────┘  │    │   Excel Processing      │  ││ │ │
│  │  │                       │    │   Data Validation       │  ││ │ │
│  │  │                       │    └─────────────────────────┘  ││ │ │
│  │  │                       └─────────────────────────────────┘│ │ │
│  │  └─────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Amazon ECR (Elastic Container Registry)                       │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Docker Images                                              │ │
│  │  ├── timecard-processor:latest                              │ │
│  │  ├── Multi-stage build (Node.js + Python)                  │ │
│  │  └── Automated CI/CD with deploy.sh                        │ │
│  └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Amazon Bedrock                                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Claude Sonnet 4 (claude-sonnet-4-20250514)                │ │
│  │  ├── Thinking Budget: 2000 tokens                          │ │
│  │  ├── Max Output: 16000 tokens                              │ │
│  │  ├── Complex Excel Analysis                                │ │
│  │  └── Federal Compliance Reasoning                          │ │
│  └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  IAM Roles & Policies                                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  App Runner Service Role                                    │ │
│  │  ├── bedrock:InvokeModel                                    │ │
│  │  ├── bedrock:ListFoundationModels                          │ │
│  │  └── logs:CreateLogGroup, logs:CreateLogStream             │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

Deployment Flow:
Local Dev → Docker Build → ECR Push → App Runner Deploy → Auto Scale
    ↓           ↓            ↓           ↓                ↓
  Port 9000   Multi-stage   Registry   Production      Load Balance
  Hot Reload  React+Flask   Storage    Port 8080       Health Check
```

## 🧠 AI Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    3-Step AI Pipeline                           │
├─────────────────────────────────────────────────────────────────┤
│  Step 1: Excel → Markdown                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │ │
│  │  │ Excel File  │→ │Table Detect │→ │   Markdown Tables   │ │ │
│  │  │ .xlsx/.xlsm │  │ Auto Headers│  │   Clean Formatting  │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Step 2: AI Extraction (Claude Sonnet 4)                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │ │
│  │  │  Markdown   │→ │   Thinking  │→ │   Structured Data   │ │ │
│  │  │  Document   │  │ 2000 tokens │  │   Compact Arrays    │ │ │
│  │  │  Full Text  │  │ Deep Analysis│  │   60% Token Saved  │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Step 3: Validation & Compliance                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │ │
│  │  │Federal Rules│→ │AI Reasoning │→ │   Human Review      │ │ │
│  │  │Daily Rate   │  │Compliance   │  │   Queue System      │ │ │
│  │  │Min Wage $58 │  │Validation   │  │   Priority Levels   │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

Token Optimization:
Traditional: {"employee": "John Doe", "date": "2025-01-15", ...} = 25 tokens
Optimized:   ["John Doe", "2025-01-15", 200.0, "Project", "Dept"] = 8 tokens
Savings:     68% reduction for large datasets (680+ entries)
```

## 🏗️ File Structure

```
timecards-extraction-validation/
├── backend/                      # Flask API server
│   ├── app.py                   # Main Flask application
│   ├── excel_to_markdown.py     # Excel to Markdown converter
│   ├── timecard_pipeline.py     # 3-step processing pipeline
│   ├── requirements.txt         # Python dependencies
│   └── venv/                    # Python virtual environment
├── frontend/                    # React web application
│   ├── src/
│   │   ├── components/          # React components (empty)
│   │   ├── pages/              # Page components (empty)
│   │   ├── utils/              # Utility functions (empty)
│   │   ├── App.js              # Main React component
│   │   ├── App.css             # Styling
│   │   └── index.js            # React entry point
│   ├── public/
│   │   └── index.html          # HTML template
│   ├── package.json            # Node.js dependencies
│   └── node_modules/           # Node.js dependencies
├── data/                       # Sample Excel files
├── sample/                     # Additional sample files (14 samples)
├── uploads/                    # File upload directory
├── .gitignore                  # Git ignore rules
└── start.sh                   # Development startup script
```

## 🚀 Quick Start

### Local Development

1. **Install dependencies and start both servers:**
   ```bash
   ./start.sh
   ```

2. **Access the application:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:9000

### AWS App Runner Deployment

1. **Prerequisites:**
   - AWS CLI configured with appropriate permissions
   - Docker installed and running
   - ECR and App Runner permissions

2. **Deploy to AWS:**
   ```bash
   ./deploy.sh
   ```

3. **The deployment script will:**
   - Create ECR repository if needed
   - Build and push Docker image
   - Create/update App Runner service
   - Configure health checks and environment variables

## 🔧 Manual Setup

### Backend (Flask)
```bash
cd backend
pip install -r requirements.txt
python app.py
```

### Frontend (React)
```bash
cd frontend
npm install
npm start
```

## 📋 Features

### ✅ Implemented
- **Excel to Markdown conversion** - Enhanced table detection and formatting
- **Claude Sonnet 4 integration** - Advanced AI extraction with thinking capabilities
- **Token-optimized format** - Compact array format for large datasets (680+ entries)
- **React frontend** - Modern UI with pagination and markdown rendering
- **Real-time processing** - Drag & drop with instant feedback
- **Sample file processing** - 16+ sample files for testing
- **Federal wage compliance** - Automated validation and reasoning
- **Currency formatting** - Professional financial display

### 🔄 Processing Pipeline
1. **Excel → Markdown** - Enhanced converter with automatic table detection
2. **AI Extraction** - Claude Sonnet 4 with 2000-token thinking budget for complex analysis
3. **Token Optimization** - Compact array format saves 60% tokens for large datasets
4. **Automated Reasoning** - Federal wage compliance validation with business rules

## 🎯 API Endpoints

- `POST /api/upload` - Upload and process Excel file
- `GET /api/samples` - List available sample files (14 samples available)
- `GET /api/process-sample/<filename>` - Process sample file
- `GET /health` - Health check

## 📁 File Structure Details

### Backend Components
- **app.py** - Flask application with CORS enabled
- **timecard_pipeline.py** - Main 3-step processing pipeline with Bedrock integration and validation
- **excel_to_markdown.py** - Enhanced Excel converter with multi-timecard support

### Sample Data
- **data/** - 2 sample Excel files for testing
- **sample/** - 14 additional sample files (Sample-1.xlsx through Sample-14.xlsx)
- **uploads/** - Directory for uploaded files (currently empty)

## 🔑 Configuration

### AWS Bedrock Setup
Set up AWS credentials for Claude Sonnet 4 access:
```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-west-2
```

### Required Permissions
- `bedrock:InvokeModel` for Claude Sonnet 4
- `bedrock:ListFoundationModels` for model discovery
- ECR and App Runner permissions for deployment

## 📊 Sample Data

Sample Excel files are located in the `data/` and `sample/` directories:
- **data/**: 2 primary sample files for testing
- **sample/**: 14 additional sample files (Sample-1.xlsx through Sample-14.xlsx)
- All files can be processed directly through the web interface

## 🎨 UI Features

### Enhanced User Experience
- **Drag & Drop Upload**: Intuitive file upload with visual feedback
- **Pagination**: Navigate through large datasets (20 entries per page)
- **Sticky Headers**: Table headers remain visible while scrolling
- **Sticky Pagination**: Navigation controls always accessible
- **Currency Formatting**: Professional financial display with commas and decimals
- **Markdown Rendering**: Toggle between raw markdown and rendered tables
- **Real-time Totals**: Live calculation of hours and wages

### Data Display
- **Employee Count**: Unique employee tracking
- **Timecard Entries**: Individual entry count with pagination
- **Total Hours**: Aggregate work hours across all entries
- **Total Wage**: Formatted currency display with proper decimals
- **Federal Compliance**: Automated wage law validation

## 🛠️ Development

### Local Development
- Backend runs on port 9000 (configured in package.json proxy)
- Frontend runs on port 3000 with hot reloading
- CORS configured for local development
- Virtual environment located in `backend/venv/`

### Production Deployment
- Single container architecture (React + Flask)
- Backend serves React build files
- Runs on port 8080 in production
- Health check endpoint: `/health`
- Auto-scaling with AWS App Runner

## 📦 Dependencies

### Backend (Python)
- Flask 3.0.0 with CORS support
- pandas ≥2.0.0 for Excel processing
- boto3 ≥1.34.0 for AWS Bedrock
- openpyxl ≥3.1.0 for Excel file handling
- tabulate ≥0.9.0 for formatting

### Frontend (React)
- React 18.2.0 with modern hooks and memoization
- axios 1.6.0 for API calls
- react-dropzone 14.2.3 for file uploads
- react-markdown 10.1.0 with remark-gfm for table rendering
- lucide-react 0.263.1 for icons
- Pagination and currency formatting
- Testing libraries included