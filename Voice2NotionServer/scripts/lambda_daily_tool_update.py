import os
import asyncio
import logging
from pathlib import Path

import boto3

# Add Voice2NotionServer to sys.path for local imports when packaged
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notion_tools import generate_and_cache_tool_metadata
from scripts.generate_notion_tool_data import upload_to_s3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DATA_FILE = Path(__file__).resolve().parent.parent / "notion_tools_data.json"


def lambda_handler(event, context):
    """AWS Lambda entrypoint to regenerate tool data and restart EB."""
    bucket = os.getenv("NOTION_TOOL_DATA_BUCKET")
    key = os.getenv("NOTION_TOOL_DATA_KEY", "notion_tools_data.json")
    eb_env = os.getenv("EB_ENVIRONMENT_NAME")  # Placeholder environment name

    if not bucket or not eb_env:
        logger.error("Missing required environment variables")
        return {"status": "error"}

    asyncio.run(generate_and_cache_tool_metadata(str(DATA_FILE)))
    upload_to_s3(str(DATA_FILE), bucket, key)

    eb = boto3.client("elasticbeanstalk")
    eb.restart_app_server(EnvironmentName=eb_env)
    logger.info("Restarted Elastic Beanstalk environment %s", eb_env)

    return {"status": "ok"}
