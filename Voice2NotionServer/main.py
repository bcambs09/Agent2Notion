from typing import Any, Dict
from fastapi import FastAPI, UploadFile, File, Body, HTTPException, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, HTTPBearer, OAuth2PasswordBearer
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
from dotenv import load_dotenv
from notion_client import AsyncClient
from notion_agent import chain
from notion_tools import (
    load_tool_data_from_env,
    run_search_agent,
    fetch_page_blocks,
    build_db_filter,
    search_notion_data,
)
from langchain_core.pydantic_v1 import BaseModel
from langchain_core.messages import HumanMessage
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(name)s: %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# Load metadata for pages/databases and filter guidance
TOOL_DATA = load_tool_data_from_env()
FILTER_GUIDE = Path(Path(__file__).resolve().parent, "query_filter_agent_prompt.txt").read_text()

app = FastAPI()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) # type: ignore

# Add security middleware
# app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])  # Configure with your domain in production

# Configure CORS with specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGINS", "*")],  # Configure with specific origins in production
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# API Key security
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_api_key(token: str = Depends(oauth2_scheme)) -> str:
    if token == os.getenv("API_KEY"):
        return token
    raise HTTPException(
        status_code=401,
        detail="Invalid API Key"
    )

# Initialize Notion client
notion = AsyncClient(auth=os.getenv("NOTION_TOKEN"))

# Get database ID from environment and validate it
NOTION_DATABASE_ID: str = os.getenv("NOTION_PAGE_ID", "")
if not NOTION_DATABASE_ID:
    raise ValueError("NOTION_PAGE_ID environment variable is not set")

class TextInput(BaseModel):
    text: str

class NotionInput(BaseModel):
    prompt: str

class SearchInput(BaseModel):
    query: str

@app.post("/add-to-notion")
@limiter.limit("10/minute")
async def add_to_notion(request: Request, input: NotionInput, api_key: str = Depends(get_api_key)):
    """Process any request to add data to Notion using the agent workflow"""
    state = {
        "messages": [HumanMessage(content=input.prompt)],
    }

    result = await chain.ainvoke(state)

    return {"message": "Request processed successfully", "result": result}


@app.post("/search-notion")
@limiter.limit("10/minute")
async def search_notion(request: Request, input: SearchInput, api_key: str = Depends(get_api_key)):
    """Run an LLM-powered search against cached Notion metadata."""
    result = await search_notion_data(input.query, notion, TOOL_DATA, FILTER_GUIDE)
    return result

@app.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request):
    """Health check endpoint"""
    return {"status": "healthy"}

@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_schema():
    """Get the OpenAPI specification"""
    return app.openapi()

# Clean up Notion client on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    await notion.aclose() 
