import os
import json
import asyncio
from typing import List, Tuple, Dict, Any

from notion_client import AsyncClient
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# Models for tool inputs
class NotionProperty(BaseModel):
    """Base model for Notion properties"""
    type: str = Field(..., description="The type of the Notion property")
    value: dict = Field(..., description="The value formatted for Notion")

class DatabaseEntryInput(BaseModel):
    """Generic input for creating a database entry"""
    properties: Dict[str, NotionProperty]

class PageTextInput(BaseModel):
    """Input for appending text to a page"""
    text: str


async def fetch_databases_and_pages(notion: AsyncClient) -> Tuple[List[dict], List[dict]]:
    """Fetch all databases and pages accessible to the integration"""
    databases: List[dict] = []
    pages: List[dict] = []

    start_cursor = None
    while True:
        resp = await notion.search(filter={"property": "object", "value": "database"}, start_cursor=start_cursor)
        databases.extend(resp.get("results", []))
        if resp.get("has_more"):
            start_cursor = resp.get("next_cursor")
        else:
            break

    start_cursor = None
    while True:
        resp = await notion.search(filter={"property": "object", "value": "page"}, start_cursor=start_cursor)
        pages.extend(resp.get("results", []))
        if resp.get("has_more"):
            start_cursor = resp.get("next_cursor")
        else:
            break

    return databases, pages


async def summarize_database(notion: AsyncClient, db: dict) -> str:
    """Create a short summary of a database combining schema and sample content"""
    # Build schema description
    props = db.get("properties", {})
    schema_parts = [f"{name} ({info.get('type')})" for name, info in props.items()]
    schema_text = ", ".join(schema_parts)

    # Fetch first few entries
    entries_resp = await notion.databases.query(database_id=db["id"], page_size=3)
    entry_titles = []
    for page in entries_resp.get("results", []):
        title_prop = next((v for k, v in page.get("properties", {}).items() if v.get("type") == "title"), None)
        if title_prop:
            texts = title_prop.get("title", [])
            if texts:
                entry_titles.append(texts[0].get("plain_text", ""))
    entries_text = "; ".join(entry_titles)

    content_for_llm = (
        f"Database name: {db.get('title', [{}])[0].get('plain_text', 'Untitled')}\n"
        f"Schema: {schema_text}\n"
        f"Example entries: {entries_text}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Summarize the provided Notion database."),
        ("human", "{text}")
    ])
    llm = ChatOpenAI(temperature=0)
    summary = (await llm.ainvoke(prompt.format_messages(text=content_for_llm))).content
    return summary


async def summarize_page(notion: AsyncClient, page: dict) -> str:
    """Create a summary of a Notion page"""
    blocks = await notion.blocks.children.list(block_id=page["id"], page_size=20)
    texts = []
    for block in blocks.get("results", []):
        typ = block.get("type")
        rich = block.get(typ, {}).get("rich_text", [])
        if rich:
            texts.append(rich[0].get("plain_text", ""))
    content = " ".join(texts)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Provide a short summary of the following page content."),
        ("human", "{text}")
    ])
    llm = ChatOpenAI(temperature=0)
    summary = (await llm.ainvoke(prompt.format_messages(text=content))).content
    return summary


def _db_tool_func(database_id: str):
    async def _func(entry: DatabaseEntryInput) -> str:
        notion = AsyncClient(auth=os.getenv("NOTION_TOKEN"))
        properties = {k: v.value for k, v in entry.properties.items()}
        await notion.pages.create(parent={"database_id": database_id}, properties=properties)
        return "Entry created"
    return _func


def _page_tool_func(page_id: str):
    async def _func(text_input: PageTextInput) -> str:
        notion = AsyncClient(auth=os.getenv("NOTION_TOKEN"))
        await notion.blocks.children.append(
            block_id=page_id,
            children=[{
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": text_input.text}}]}
            }]
        )
        return "Text added to page"
    return _func


async def build_tool_metadata() -> List[Dict[str, Any]]:
    """Return metadata for all databases and pages accessible to the integration."""
    notion = AsyncClient(auth=os.getenv("NOTION_TOKEN"))
    databases, pages = await fetch_databases_and_pages(notion)
    metadata: List[Dict[str, Any]] = []

    for db in databases:
        summary = await summarize_database(notion, db)
        metadata.append({"id": db["id"], "type": "database", "summary": summary})

    for page in pages:
        summary = await summarize_page(notion, page)
        metadata.append({"id": page["id"], "type": "page", "summary": summary})

    await notion.aclose()
    return metadata


async def generate_notion_tools() -> List[StructuredTool]:
    """Generate StructuredTools directly from the Notion API."""
    metadata = await build_tool_metadata()
    return build_tools_from_data(metadata)


async def generate_and_cache_tool_metadata(file_path: str) -> List[Dict[str, Any]]:
    """Generate tool metadata and save it to a JSON file."""
    metadata = await build_tool_metadata()
    with open(file_path, "w") as f:
        json.dump(metadata, f, indent=2)
    return metadata


def load_tool_data(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, "r") as f:
        return json.load(f)


def build_tools_from_data(data: List[Dict[str, Any]]) -> List[StructuredTool]:
    tools: List[StructuredTool] = []
    for item in data:
        if item["type"] == "database":
            func = _db_tool_func(item["id"])
        else:
            func = _page_tool_func(item["id"])
        tools.append(
            StructuredTool.from_function(
                coroutine=func,
                name=f"{item['type']}_{item['id'].replace('-', '')}",
                description=item["summary"],
            )
        )
    return tools
