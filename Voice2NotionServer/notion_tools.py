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
    llm = ChatOpenAI(temperature=0, model="gpt-4o")
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
    llm = ChatOpenAI(temperature=0, model="gpt-4o")
    summary_raw = (await llm.ainvoke(prompt.format_messages(text=content_for_llm))).content
    # Ensure the returned value is a string to satisfy type checkers.
    return str(summary_raw)


async def fetch_page_blocks(notion: AsyncClient, page_id: str) -> List[dict]:
    """Return all block objects for the given page."""
    blocks: List[dict] = []
    cursor = None
    while True:
        resp = await notion.blocks.children.list(block_id=page_id, start_cursor=cursor)
        blocks.extend(resp.get("results", []))
        if resp.get("has_more"):
            cursor = resp.get("next_cursor")
        else:
            break
    return blocks


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

def load_tool_data(path: str | None) -> List[Dict[str, Any]]:
    """Load tool metadata from a local file or S3 object.

    Args:
        path: Local filesystem path or ``s3://bucket/key``. If ``None``,
            defaults to ``notion_tools_data.json`` next to this module.

    Returns:
        Parsed JSON data from the given path.
    """
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "notion_tools_data.json")

    if path.startswith("s3://"):
        import boto3

        bucket, key = path[5:].split("/", 1)
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read().decode("utf-8")
        return json.loads(data)

    with open(path, "r") as f:
        return json.load(f)


async def generate_tool_metadata_json() -> str:
    """Return the metadata as a pretty-printed JSON string (no disk I/O)."""
    metadata = await build_tool_metadata()
    return json.dumps(metadata, indent=2)


def load_tool_data_from_env() -> List[Dict[str, Any]]:
    """Load tool metadata using the ``NOTION_TOOL_DATA_PATH`` environment variable."""
    data_path = os.getenv("NOTION_TOOL_DATA_PATH")
    return load_tool_data(data_path)


class SearchAgentOutput(BaseModel):
    """IDs for relevant pages and databases."""
    page_ids: List[str] = Field(default_factory=list)
    database_ids: List[str] = Field(default_factory=list)


async def run_search_agent(query: str, tool_data: List[Dict[str, Any]]) -> SearchAgentOutput:
    """Use an LLM to select relevant pages and databases from ``tool_data``."""
    items_summary = "\n".join(
        f"- {item['id']} ({item['type']}): {item.get('title', 'Untitled')} - {item.get('summary', '')}"
        for item in tool_data
    )

    system = (
        "Select the IDs of any pages or databases that are relevant to the user query. "
        "Only return IDs from the provided list in JSON format with 'page_ids' and 'database_ids'."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system + "\nAvailable items:\n" + items_summary),
        ("human", "The query to select relevant items from the list is: {query}"),
    ])

    llm = ChatOpenAI(temperature=0, model="gpt-4o").with_structured_output(SearchAgentOutput)
    return await llm.ainvoke(prompt.format_messages(query=query))


async def build_db_filter(query: str, schema_json: str, guide_text: str) -> Dict[str, Any]:
    """Generate a Notion database filter object using an LLM."""
    # ChatPromptTemplate uses Python str.format under the hood to substitute
    # placeholders (e.g. "{query}"). Any literal curly-brace characters that
    # appear in the `guide_text` therefore need to be escaped ("{{" / "}}").
    # Otherwise the template engine will attempt to treat them as additional
    # placeholders and raise a KeyError (for example on a string like
    # "{"equals": true}").

    system = guide_text.replace("{", "{{").replace("}", "}}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", "Query: {query}\nSchema: {schema}"),
    ])

    llm = ChatOpenAI(temperature=0, model="gpt-4o", model_kwargs={"response_format": {"type": "json_object"}})
    resp = await llm.ainvoke(prompt.format_messages(query=query, schema=schema_json))

    try:
        data = json.loads(resp.content)
        if not isinstance(data, dict):
            raise ValueError("Filter is not a JSON object")
    except Exception as e:
        logger.error("Invalid filter response from LLM: %s", e)
        raise
    return data


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

# === High-level search helper =================================================
# This function centralises the logic originally implemented inside the FastAPI
# endpoint in main.py so that it can be reused in other contexts (e.g. unit
# tests, CLI tools, etc.) and keeps main.py thin.

async def search_notion_data(
    query: str,
    notion: AsyncClient,
    tool_data: List[Dict[str, Any]],
    filter_guide: str,
) -> Dict[str, Any]:
    """Run an LLM-powered search over Notion content.

    Parameters
    ----------
    query : str
        The natural-language query provided by the caller.
    notion : AsyncClient
        An already-configured Notion client instance.
    tool_data : List[Dict[str, Any]]
        Cached metadata describing pages and databases (as produced by
        ``build_tool_metadata`` and persisted via ``generate_tool_metadata_json``).
    filter_guide : str
        Prompt text that guides the LLM when building database filter objects.

    Returns
    -------
    Dict[str, Any]
        A mapping with two keys:
        * ``"pages"`` – mapping of page_id → list[block] (full block objects).
        * ``"databases"`` – mapping of database_id → query results returned by
          the Notion API for that DB (after applying an LLM-generated filter).
    """
    logger.info("Running search agent for query: %s", query)

    # Ask the LLM which pages and databases are relevant.
    agent_out = await run_search_agent(query, tool_data)

    pages: Dict[str, Any] = {}
    databases: Dict[str, Any] = {}

    # Fetch full block contents for each relevant page so that the caller
    # receives the complete context and can decide what to display.
    for pid in agent_out.page_ids:
        pages[pid] = await fetch_page_blocks(notion, pid)

    # For databases we need an additional step: build a filter so that the
    # resulting query only returns rows that match the user's intent.
    for dbid in agent_out.database_ids:
        # tool_data items store the raw Notion schema JSON (a *string*).
        raw_schema = next((it.get("schema") for it in tool_data if it["id"] == dbid), None)
        schema_json: str = raw_schema if isinstance(raw_schema, str) else "{}"

        filter_obj = await build_db_filter(query, schema_json, filter_guide)
        databases[dbid] = await notion.databases.query(database_id=dbid, filter=filter_obj["filter"])

    return {"pages": pages, "databases": databases}
