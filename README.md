# Voice2Notion

A voice-first AI agent that turns natural language (spoken or typed) into structured Notion content.
The backend is a FastAPI server powered by a LangGraph workflow that can reason over your request and
call dynamically-generated tools that map directly to your personal Notion workspace.

---

## 🗺  High-Level Architecture

```
Client ─▶ /add-to-notion  ─┐
                         │   1.  FastAPI receives the prompt
                         ▼
               ┌────────────────────┐
               │  LangGraph Agent   │
               └────────────────────┘
                  ▲            │
      reasoning   │  tool call │ execution
                  │            ▼
               ┌────────────────────┐
               │  Notion API Tools  │
               └────────────────────┘
                         │
                         ▼
                     Notion
```

1. **FastAPI endpoint** `/add-to-notion` accepts a prompt and places it into an `AgentState`.
2. **LangGraph workflow** (`notion_agent.py`) orchestrates two nodes:
   * `notion_chat` – a GPT-4o reasoning step bound to the available tools.
   * `tools` – executes whichever tool the model selects.
3. **Tool catalogue**
   * **Static tools**: `create_new_task`, `add_to_movie_list`.
   * **Dynamic tools**: At start-up `notion_tools.py` scans every database & page your Notion token
     can access, creates a `StructuredTool` for each, and stores a lightweight description in
     `notion_tools_data.json` for fast reloads.
4. The graph loops ⟲ between `notion_chat` and `tools` until the model signals `END`, then the server
   returns the final state to the caller.

---

## 🚀 Quick-start

### Requirements
* Python 3.10+
* An **OpenAI** API key with GPT-4 access
* A **Notion** integration token with write permissions to the pages/databases you want to modify

### Installation
```bash
# 1. Get the code
$ git clone <repo>
$ cd Voice2Notion/Voice2NotionServer

# 2. Create and activate virtual-env
$ python -m venv venv
$ source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
$ pip install -r requirements.txt

# 4. Environment variables (create .env)
OPENAI_API_KEY=sk-...
NOTION_TOKEN=secret_...
NOTION_PAGE_ID=<default_database_for_tasks>
NOTION_MOVIE_DATABASE_ID=<movie_database_id_if_used>
API_KEY=test-key               # used by the endpoint security
ALLOWED_ORIGINS=*              # (optional) CORS
NOTION_TOOL_DATA_BUCKET=<s3_bucket_for_tool_data>
NOTION_TOOL_DATA_KEY=notion_tools_data.json   # (optional)
NOTION_TOOL_DATA_PATH=./notion_tools_data.json  # (optional local override)
```
If `NOTION_TOOL_DATA_PATH` is not set, the server will load `notion_tools_data.json` from the specified S3 bucket/key.

### (Optional) Pre-generate dynamic tool metadata
Generating the summaries for every database/page can take >30 s the very first time. Run once and cache locally or upload to S3:
```bash
# Local file
$ python scripts/generate_notion_tool_data.py
# Upload directly to S3
$ python scripts/generate_notion_tool_data.py --bucket <your-bucket>
```

### Run the server
```bash
$ uvicorn main:app --reload  # http://localhost:8000
```

---

## 📡 Sending a Test Request

### Using *curl*
```bash
curl -X POST http://localhost:8000/add-to-notion \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{
        "prompt": "Add a task: Draft the Q2 report by next Friday with high priority."
      }'
```
A typical successful response looks like:
```json
{
  "message": "Request processed successfully",
  "result": {
    "messages": [
      {
        "type": "ai",
        "content": "Created task in Notion."
      }
    ]
  }
}
```

### Using the helper script
```bash
$ python scripts/send_test_request.py
```
The script reads `SERVER_URL` and `API_KEY` from your environment (falls back to localhost/test-key).

### Searching Notion
```bash
curl -X POST http://localhost:8000/search-notion \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "meeting notes"}'
```

---

## 🛠  Extending the Agent
1. **Add a new static tool**: implement an async function, then wrap it with `StructuredTool.from_function` in `notion_agent.py`.
2. **Expose more of your workspace**: simply share additional pages/databases with the integration token and rerun `generate_notion_tool_data.py`.
3. **Adjust the prompt** in `notion_agent.py` to change how the model reasons about tasks.

---

## 🩺 Health Check
`GET /health` → `{ "status": "healthy" }`

---

## License
MIT © 2024
