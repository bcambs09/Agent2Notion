source .env

TARGET_ID="1"

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
  --source-arn arn:aws:events:${AWS_REGION}:${AWS_ACCOUNT_ID}:rule/${RULE_NAME} \
  --region ${AWS_REGION}
