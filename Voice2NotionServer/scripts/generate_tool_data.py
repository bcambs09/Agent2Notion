import os
import asyncio
from notion_client import AsyncClient
from notion_tools import (
    fetch_databases_and_pages,
    summarize_database,
    summarize_page,
    save_tool_data,
)


async def main() -> None:
    notion = AsyncClient(auth=os.getenv("NOTION_TOKEN"))
    databases, pages = await fetch_databases_and_pages(notion)
    data = {"databases": [], "pages": []}

    for db in databases:
        summary = await summarize_database(notion, db)
        data["databases"].append({
            "id": db["id"],
            "name": f"database_{db['id'].replace('-', '')}",
            "description": summary,
        })

    for page in pages:
        summary = await summarize_page(notion, page)
        data["pages"].append({
            "id": page["id"],
            "name": f"page_{page['id'].replace('-', '')}",
            "description": summary,
        })

    save_tool_data(data)
    await notion.aclose()


if __name__ == "__main__":
    asyncio.run(main())
