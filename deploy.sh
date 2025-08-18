#!/bin/bash

# Cast & Crew Timecard Processor - AWS App Runner Deployment Script

set -e

echo "🚀 Deploying Cast & Crew Timecard Processor to AWS App Runner..."

# Configuration
APP_NAME="timecard-processor"
REGION="us-west-2"
ECR_REPO_NAME="timecard-processor"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}📋 Configuration:${NC}"
echo -e "  App Name: ${APP_NAME}"
echo -e "  Region: ${REGION}"
echo -e "  ECR Repository: ${ECR_REPO_NAME}"
echo ""

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}"

echo -e "${BLUE}🔍 AWS Account ID: ${ACCOUNT_ID}${NC}"
echo -e "${BLUE}🐳 ECR URI: ${ECR_URI}${NC}"
echo ""

# Create ECR repository if it doesn't exist
echo -e "${YELLOW}📦 Creating ECR repository if needed...${NC}"
aws ecr describe-repositories --repository-names ${ECR_REPO_NAME} --region ${REGION} 2>/dev/null || \
aws ecr create-repository --repository-name ${ECR_REPO_NAME} --region ${REGION}

# Get ECR login token
echo -e "${YELLOW}🔐 Logging into ECR...${NC}"
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_URI}

# Build Docker image
echo -e "${YELLOW}🏗️  Building Docker image...${NC}"
docker build -t ${ECR_REPO_NAME} .

# Tag image for ECR
echo -e "${YELLOW}🏷️  Tagging image...${NC}"
docker tag ${ECR_REPO_NAME}:latest ${ECR_URI}:latest

# Push to ECR
echo -e "${YELLOW}📤 Pushing image to ECR...${NC}"
docker push ${ECR_URI}:latest

echo -e "${GREEN}✅ Docker image pushed successfully!${NC}"
echo -e "${GREEN}🐳 Image URI: ${ECR_URI}:latest${NC}"
echo ""

# Create App Runner service configuration
cat > apprunner-service.json << EOF
{
  "ServiceName": "${APP_NAME}",
  "SourceConfiguration": {
    "ImageRepository": {
      "ImageIdentifier": "${ECR_URI}:latest",
      "ImageConfiguration": {
        "Port": "8080",
        "RuntimeEnvironmentVariables": {
          "PORT": "8080",
          "FLASK_ENV": "production",
          "AWS_DEFAULT_REGION": "${REGION}"
        }
      },
      "ImageRepositoryType": "ECR"
    },
    "AutoDeploymentsEnabled": false
  },
  "InstanceConfiguration": {
    "Cpu": "1 vCPU",
    "Memory": "2 GB"
  },
  "HealthCheckConfiguration": {
    "Protocol": "HTTP",
    "Path": "/health",
    "Interval": 10,
    "Timeout": 5,
    "HealthyThreshold": 1,
    "UnhealthyThreshold": 5
  }
}
EOF

# Check if App Runner service exists
SERVICE_ARN=$(aws apprunner list-services --region ${REGION} --query "ServiceSummaryList[?ServiceName=='${APP_NAME}'].ServiceArn" --output text)

if [ -z "$SERVICE_ARN" ]; then
    echo -e "${YELLOW}🆕 Creating new App Runner service...${NC}"
    aws apprunner create-service --cli-input-json file://apprunner-service.json --region ${REGION}
    echo -e "${GREEN}✅ App Runner service created!${NC}"
else
    echo -e "${YELLOW}🔄 Updating existing App Runner service...${NC}"
    aws apprunner update-service --service-arn ${SERVICE_ARN} --source-configuration file://apprunner-service.json --region ${REGION}
    echo -e "${GREEN}✅ App Runner service updated!${NC}"
fi

# Clean up temporary file
rm -f apprunner-service.json

echo ""
echo -e "${GREEN}🎉 Deployment completed!${NC}"
echo -e "${BLUE}📱 Your app will be available at the App Runner service URL${NC}"
echo -e "${BLUE}🔍 Check the AWS Console for the service URL and status${NC}"
echo ""
echo -e "${YELLOW}💡 Useful commands:${NC}"
echo -e "  aws apprunner list-services --region ${REGION}"
echo -e "  aws apprunner describe-service --service-arn <SERVICE_ARN> --region ${REGION}"