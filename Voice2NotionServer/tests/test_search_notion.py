import os
from pathlib import Path
import sys
import asyncio
from typing import cast

# ---------------------------------------------------------------------------
# Load the search helper from the project package.
# ---------------------------------------------------------------------------

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from notion_tools import (
    load_tool_data_from_env,
    search_notion_data,
    SearchAgentOutput,
)
from notion_client import AsyncClient



# ---------------------------------------------------------------------------
# Environment variables expected by the Notion client / app.
# ---------------------------------------------------------------------------

os.environ.setdefault("NOTION_TOKEN", "dummy-token")


async def _async_main() -> None:
    tools = load_tool_data_from_env()
    filter_guide = Path(Path(__file__).resolve().parent.parent, "query_filter_agent_prompt.txt").read_text()
    result = await search_notion_data(
        query="What are all my incomplete tasks with a priority of Today?",
        notion=AsyncClient(auth=os.environ.get("NOTION_TOKEN")),
        tool_data=tools,
        filter_guide=filter_guide,
        db_instructions={},
    )

    print("search_notion_data returned:")
    print(result)


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        print("Cancelled by user.")
        sys.exit(1)


if __name__ == "__main__":
    main() 