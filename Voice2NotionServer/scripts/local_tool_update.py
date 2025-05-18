import sys
import os
from pathlib import Path
import asyncio
import argparse
import logging

import boto3

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(name)s: %(message)s')

# Add the parent directory (Voice2NotionServer) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notion_tools import generate_and_cache_tool_metadata


DATA_FILE = Path(__file__).resolve().parent.parent / "notion_tools_data.json"


def upload_to_s3(file_path: str, bucket: str, key: str) -> None:
    """Upload the generated file to S3."""
    s3 = boto3.client("s3")
    s3.upload_file(file_path, bucket, key)
    logging.getLogger(__name__).info("Uploaded %s to s3://%s/%s", file_path, bucket, key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate tool metadata and optionally upload to S3"
    )
    parser.add_argument("--bucket", help="S3 bucket to upload the data to")
    parser.add_argument(
        "--key",
        default="notion_tools_data.json",
        help="S3 object key (default: notion_tools_data.json)",
    )
    args = parser.parse_args()

    asyncio.run(generate_and_cache_tool_metadata(str(DATA_FILE)))

    if args.bucket:
        upload_to_s3(str(DATA_FILE), args.bucket, args.key)
