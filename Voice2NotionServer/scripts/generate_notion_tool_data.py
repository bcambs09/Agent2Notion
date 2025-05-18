import asyncio
import os
from pathlib import Path
from notion_tools import generate_and_cache_tool_metadata

DATA_FILE = Path(__file__).resolve().parent.parent / "notion_tools_data.json"

if __name__ == "__main__":
    asyncio.run(generate_and_cache_tool_metadata(str(DATA_FILE)))
    print(f"Tool metadata written to {DATA_FILE}")
