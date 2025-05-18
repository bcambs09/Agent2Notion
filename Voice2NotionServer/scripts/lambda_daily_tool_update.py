import os
import asyncio
import logging
logging.getLogger().setLevel(logging.INFO)
from pathlib import Path

import boto3

# Add Voice2NotionServer to sys.path for local imports when packaged
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notion_tools import generate_tool_metadata_json

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent / "notion_tools_data.json"


def upload_json_to_s3(json_str: str, bucket: str, key: str) -> None:
    """Upload the JSON payload directly to S3 without touching disk."""
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json_str.encode("utf-8"),
        ContentType="application/json",
    )
    logging.getLogger(__name__).info("Uploaded %s bytes to s3://%s/%s",
                                     len(json_str), bucket, key)


def lambda_handler(event, context):
    """AWS Lambda entrypoint to regenerate tool data and restart EB."""
    bucket = os.getenv("NOTION_TOOL_DATA_BUCKET")
    key = os.getenv("NOTION_TOOL_DATA_KEY", "notion_tools_data.json")
    eb_env = os.getenv("EB_ENVIRONMENT_NAME")  # Placeholder environment name
    # Set secrets from AWS secret manager
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId="NOTION_TOKEN")
    os.environ["NOTION_TOKEN"] = response["SecretString"]
    response = client.get_secret_value(SecretId="OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = response["SecretString"]

    if not bucket or not eb_env:
        logger.error("Missing required environment variables")
        return {"status": "error"}

    metadata_json = asyncio.run(generate_tool_metadata_json())
    upload_json_to_s3(metadata_json, bucket, key)

    eb = boto3.client("elasticbeanstalk")
    eb.restart_app_server(EnvironmentName=eb_env)
    logger.info("Restarted Elastic Beanstalk environment %s", eb_env)

    return {"status": "ok"}
