import os
import json
import asyncio
import re
from typing import List, Tuple, Dict, Any

import boto3

from notion_client import AsyncClient
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from logging import getLogger
logger = getLogger(__name__)

# Models for tool inputs
class NotionProperty(BaseModel):
    """Base model for Notion properties"""
    type: str = Field(..., description="The type of the Notion property")
    value: dict = Field(..., description="The value formatted for Notion")

class DatabaseEntryInput(BaseModel):
    """Generic input for creating a database entry.

    The "properties" field accepts a mapping from property name to either:
    1. A NotionProperty object (containing "type" and "value" keys), **or**
    2. A raw dictionary that is already formatted for the Notion API.

    This relaxation makes it easier for LLMs or external callers to supply
    simple JSON payloads without having to wrap every value in the
    NotionProperty helper model.
    """
    # Accept either the strongly-typed NotionProperty model or a plain
    # dictionary that conforms to Notion's API.
    properties: Dict[str, Any] | None = None

    model_config = {
        "extra": "allow"  # Permit additional fields when using the flat style
    }

class PageTextInput(BaseModel):
    """Input for appending text to a page"""
    text: str




def get_page_title(page_data: dict) -> str | None:
    """
    Parses the page title from a Notion page data dictionary.

    Args:
        page_data: A dictionary representing Notion page data.

    Returns:
        The page title as a string, or None if the title cannot be found.
    """
    try:
        title_property = page_data.get("properties", {}).get("title", {})
        if title_property and title_property.get("type") == "title":
            title_list = title_property.get("title", [])
            if title_list and isinstance(title_list, list) and len(title_list) > 0:
                first_title_item = title_list[0]
                if first_title_item and isinstance(first_title_item, dict):
                    return first_title_item.get("plain_text")
        return None  # Return None if the structure is not as expected
    except (AttributeError, IndexError, TypeError) as e:
        print(f"Error parsing page title: {e}")
        return None


async def fetch_databases_and_pages(notion: AsyncClient) -> Tuple[List[dict], List[dict]]:
    """Fetch all databases and pages accessible to the integration"""
    databases: List[dict] = []
    pages: List[dict] = []

    start_cursor = None
    while True:
        resp = await notion.search(filter={"property": "object", "value": "database"}, start_cursor=start_cursor)
        results = resp.get("results", [])
        databases.extend(results)
        logger.info(f"Fetched {len(databases)} databases")
        if resp.get("has_more"):
            start_cursor = resp.get("next_cursor")
        else:
            break

    start_cursor = None
    while True:
        resp = await notion.search(filter={"property": "object", "value": "page"}, start_cursor=start_cursor)
        results = resp.get("results", [])
        results = [r for r in results if r.get("parent", {}).get("type") != "database_id"]
        pages.extend(results)
        for p in results:
            logger.info(get_page_title(p))
        logger.info(f"Fetched {len(pages)} pages")
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
    summary_raw = (await llm.ainvoke(prompt.format_messages(text=content_for_llm))).content
    return str(summary_raw)


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

    # Include the page title to give the LLM more context when producing the summary.
    page_title = get_page_title(page) or "Untitled"
    content_for_llm = f"Page title: {page_title}\nPage content: {content}"

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Provide a short summary of the following page content."),
        ("human", "{text}")
    ])
    llm = ChatOpenAI(temperature=0)
    summary_raw = (await llm.ainvoke(prompt.format_messages(text=content_for_llm))).content
    # Ensure the returned value is a string to satisfy type checkers.
    return str(summary_raw)


def _db_tool_func(database_id: str):
    async def _func(entry: DatabaseEntryInput) -> str:
        notion = AsyncClient(auth=os.getenv("NOTION_TOKEN"))

        # Determine the raw property mapping supplied by the caller. We support
        # two styles:
        # 1. The "preferred" style where everything lives under a top-level
        #    "properties" key (entry.properties is not None).
        # 2. A flat style where the caller puts property names at the top
        #    level of the JSON payload (entry.properties is None). This is the
        #    style produced by many LLM calls when they ignore the helper
        #    model structure.

        raw_props: Dict[str, Any]
        if entry.properties is not None:
            raw_props = entry.properties
        else:
            # Fall back to every field except "properties" itself.
            raw_props = {k: v for k, v in entry.model_dump().items() if k != "properties"}

        processed_properties: Dict[str, Any] = {}
        for key, val in raw_props.items():
            if isinstance(val, dict):
                # Assume the caller already supplied a correctly-formatted
                # Notion property dictionary (e.g. {"title": [...]}).
                processed_properties[key] = val
            elif isinstance(val, NotionProperty):
                processed_properties[key] = val.value
            else:
                raise ValueError(
                    f"Unsupported property type for '{key}': {type(val)}. "
                    "Expected dict or NotionProperty."
                )

        await notion.pages.create(parent={"database_id": database_id}, properties=processed_properties)
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
    logger.info("Fetching databases and pages")
    databases, pages = await fetch_databases_and_pages(notion)
    metadata: List[Dict[str, Any]] = []

    for db in databases:
        summary = await summarize_database(notion, db)
        logger.info(f"Summarized database {db['id']}: {summary}")

        # Extract the display title of the database for easier reference.
        db_title = db.get("title", [{}])[0].get("plain_text", "Untitled")

        # Include the raw Notion schema as a separate JSON-encoded string so that callers can
        # access an exact representation of the database schema without having to parse the
        # human-readable summary. Only database items include this additional field.
        schema_json = json.dumps(db.get("properties", {}))

        metadata.append({
            "id": db["id"],
            "type": "database",
            "title": db_title,
            "summary": summary,
            "schema": schema_json,
        })

    for page in pages:
        summary = await summarize_page(notion, page)
        logger.info(f"Summarized page {page['id']}: {summary}")

        page_title = get_page_title(page) or "Untitled"

        metadata.append({
            "id": page["id"],
            "type": "page",
            "title": page_title,
            "summary": summary,
        })

    await notion.aclose()
    return metadata


async def generate_and_cache_tool_metadata(file_path: str) -> List[Dict[str, Any]]:
    """Generate tool metadata and save it to a JSON file."""
    metadata = await build_tool_metadata()
    with open(file_path, "w") as f:
        json.dump(metadata, f, indent=2)
    return metadata

def _load_from_file(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, "r") as f:
        return json.load(f)


def _load_from_s3(bucket: str, key: str) -> List[Dict[str, Any]]:
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read())


def load_tool_data(file_path: str | None = None) -> List[Dict[str, Any]]:
    """Load tool metadata from a local file or from S3 if file_path is None."""
    if file_path:
        return _load_from_file(file_path)
    bucket = os.getenv("NOTION_TOOL_DATA_BUCKET")
    if not bucket:
        raise ValueError("NOTION_TOOL_DATA_BUCKET environment variable is required")
    key = os.getenv("NOTION_TOOL_DATA_KEY", "notion_tools_data.json")
    return _load_from_s3(bucket, key)


def build_tools_from_data(data: List[Dict[str, Any]]) -> List[StructuredTool]:
    tools: List[StructuredTool] = []
    name_set = set()
    for item in data:
        if item["type"] == "database":
            func = _db_tool_func(item["id"])
        else:
            func = _page_tool_func(item["id"])
        # Build a rich description that starts with the item's title, followed by the human-readable
        # summary. If the item represents a database, also append the raw JSON schema so that
        # downstream agents have full access to the database structure.
        title = item.get("title", "Untitled")
        description_parts = [f"Title: {title}", item.get("summary", "")]
        if item.get("type") == "database" and "schema" in item:
            description_parts.append(f"Schema (JSON):\n{item['schema']}")

        description = "\n\n".join(description_parts).strip()

        raw_name = f"{title}_{item['type']}_add"
        # Remove any characters not matching the allowed pattern: letters, numbers, underscores, or hyphens.
        name = re.sub(r'[^a-zA-Z0-9_-]', '', raw_name)
        if name not in name_set:
            name_set.add(name)        
            tools.append(
                StructuredTool.from_function(
                    coroutine=func,
                    name=name,
                    description=description,
                )
            )
    return tools
