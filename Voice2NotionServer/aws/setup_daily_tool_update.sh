#!/bin/bash
# Create a Lambda function and EventBridge rule to run daily.
# Fill in the placeholders (<...>) before executing.

set -euo pipefail

AWS_REGION="us-east-1"
CODE_KEY="lambda/agent2notion-daily-tool-update.zip"

source .env

# Upload packaged lambda code
aws s3 cp Agent2NotionServer/scripts/lambda_daily_tool_update.zip s3://${SCHEMA_REFRESH_CODE_BUCKET}/${CODE_KEY} --region ${AWS_REGION}

# Create the Lambda function
aws lambda create-function \
  --function-name ${LAMBDA_NAME} \
  --runtime python3.11 \
  --role ${LAMBDA_EXECUTION_ROLE_ARN} \
  --handler lambda_daily_tool_update.lambda_handler \
  --code S3Bucket=${SCHEMA_REFRESH_CODE_BUCKET},S3Key=${CODE_KEY} \
  --region ${AWS_REGION}

echo "Daily tool update setup complete."
