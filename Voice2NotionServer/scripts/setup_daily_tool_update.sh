#!/bin/bash
# Create a Lambda function and EventBridge rule to run daily.
# Fill in the placeholders (<...>) before executing.

set -euo pipefail

AWS_REGION="us-east-1"
LAMBDA_NAME="voice2notion-daily-tool-update"
ROLE_ARN="<LAMBDA_EXECUTION_ROLE_ARN>"            # TODO: replace
CODE_BUCKET="<CODE_S3_BUCKET>"                     # TODO: replace
CODE_KEY="lambda/voice2notion-daily-tool-update.zip"  # TODO: adjust if needed
RULE_NAME="voice2notion-daily-tool-update"
TARGET_ID="1"
LAMBDA_ARN="<LAMBDA_FUNCTION_ARN>"                 # TODO: will be returned after creation

# Upload packaged lambda code
aws s3 cp lambda_daily_tool_update.zip s3://${CODE_BUCKET}/${CODE_KEY} --region ${AWS_REGION}

# Create the Lambda function
aws lambda create-function \
  --function-name ${LAMBDA_NAME} \
  --runtime python3.11 \
  --role ${ROLE_ARN} \
  --handler lambda_daily_tool_update.lambda_handler \
  --code S3Bucket=${CODE_BUCKET},S3Key=${CODE_KEY} \
  --region ${AWS_REGION}

# Create daily EventBridge rule (runs at 00:00 UTC)
aws events put-rule \
  --name ${RULE_NAME} \
  --schedule-expression "cron(0 0 * * ? *)" \
  --region ${AWS_REGION}

# Add Lambda target to the rule
aws events put-targets \
  --rule ${RULE_NAME} \
  --targets "Id"="${TARGET_ID}","Arn"="${LAMBDA_ARN}" \
  --region ${AWS_REGION}

# Allow EventBridge to invoke the Lambda function
aws lambda add-permission \
  --function-name ${LAMBDA_NAME} \
  --statement-id ${RULE_NAME}-invoke \
  --action 'lambda:InvokeFunction' \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:${AWS_REGION}:<ACCOUNT_ID>:rule/${RULE_NAME} \
  --region ${AWS_REGION}

echo "Daily tool update setup complete."
