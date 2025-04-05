from fastapi import FastAPI, UploadFile, File, Body, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
from dotenv import load_dotenv
from notion_client import AsyncClient
from notion_agent import chain
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
load_dotenv()

app = FastAPI()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) # type: ignore

# Add security middleware
app.add_middleware(HTTPSRedirectMiddleware)
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
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

async def get_api_key(api_key_header: str = Security(api_key_header)) -> str:
    if api_key_header == os.getenv("API_KEY"):
        return api_key_header
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

@app.post("/process-audio")
@limiter.limit("5/minute")
async def process_audio(file: UploadFile = File(...), api_key: str = Depends(get_api_key)):
    """Process audio file and create Notion content"""
    # TODO: Implement audio processing with Whisper
    return {"message": "Audio processing endpoint ready for implementation"}

@app.post("/process-text")
@limiter.limit("10/minute")
async def process_text(input: TextInput, api_key: str = Depends(get_api_key)):
    """Process text input and create Notion content using the agent workflow"""
    # Initialize the state
    state = {
        "messages": [HumanMessage(content=input.text)],
    }
    
    # Run the workflow
    result = await chain.ainvoke(state)
    
    return {"message": "Text processed successfully", "result": result}

@app.get("/health")
@limiter.limit("30/minute")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

# Clean up Notion client on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    await notion.aclose() 