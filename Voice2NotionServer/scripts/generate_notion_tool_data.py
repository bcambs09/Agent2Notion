import sys
import os
from pathlib import Path
import asyncio
import logging
# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(name)s: %(message)s')


# Add the parent directory (Voice2NotionServer) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notion_tools import generate_and_cache_tool_metadata

DATA_FILE = Path(__file__).resolve().parent.parent / "notion_tools_data.json"

if __name__ == "__main__":
    asyncio.run(generate_and_cache_tool_metadata(str(DATA_FILE)))
