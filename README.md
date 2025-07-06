# Agent2Notion

An AI-first API, fine-tuned to your Notion workspace.

Either as an initial manual step or as a recurring daily job, Agent2Notion scans your Notion workspace for pages and databases, generating custom descriptions for each. These descriptions become the basis for agentic tool calls that add new database entries or page content to your workspace.

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
   * **Dynamic tools**: `notion_tools.py` runs as a daily cron job, scanning every database & page your Notion token
     can access. The cron job creates a `StructuredTool` for each with a relevant description.
4. The graph loops ⟲ between `notion_chat` and `tools` until the model signals `END`, then the server
   returns the final state to the caller.

---

## 🚀 Quick-start

### Requirements
* Python 3.10+
* An **OpenAI** API key
* A **Notion** integration token with write permissions to the pages/databases you want to modify

### Installation
```bash
# 1. Get the code
$ git clone <repo>
$ cd Agent2Notion/Agent2NotionServer

# 2. Create and activate virtual-env
$ python -m venv venv
$ source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies
$ pip install -r requirements.txt

# 4. Environment variables (create .env)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o              # (optional) default model name
NOTION_TOKEN=secret_...
API_KEY=test-key               # used for FastAPI authentication
ALLOWED_ORIGINS=*              # (optional) CORS
NOTION_TOOL_DATA_BUCKET=<s3_bucket_for_tool_data>  # defaults to "notionserver"
NOTION_TOOL_DATA_KEY=notion_tools_data.json   # (optional)
NOTION_TOOL_DATA_PATH=./path/to/tools/json/file  # (optional local override)
NOTION_DB_INSTRUCTIONS_PATH=./db_custom_instructions.json  # (optional local override)
EB_ENVIRONMENT_NAME=<elastic_beanstalk_env>  # used by the daily refresh Lambda (see description below)
LAMBDA_EXECUTION_ROLE_ARN="<LAMBDA_EXECUTION_ROLE_ARN>"
SCHEMA_REFRESH_CODE_BUCKET="<SCHEMA_REFRESH_CODE_BUCKET>" # defaults to "notionserver"
LAMBDA_NAME="<DESIRED_SCHEMA_UPDATE_LAMBDA_NAME>"
LAMBDA_ARN="<CREATED_LAMBDA_ARN>"
RULE_NAME="<DESIRED_CRON_RULE_NAME>"
```
If `NOTION_TOOL_DATA_PATH` is not set, the server loads `notion_tools_data.json` from the specified S3 bucket/key.
If `NOTION_DB_INSTRUCTIONS_PATH` is not set, the server loads `db_custom_instructions.json` from the same S3 bucket. Set the variable to use a local override instead.

### (Optional) Pre-generate dynamic tool metadata
Generating the summaries for every database/page can take >30 s the very first time. Run once and cache locally or upload to S3:
```bash
# Local file
$ python scripts/generate_notion_tool_data.py
# Upload directly to S3
$ python scripts/generate_notion_tool_data.py --bucket <your-bucket>
```

### Server deployment
You can deploy the FastAPI server wherever you'd like, but Agent2Notion is optimized for AWS because of the automated update Lambda (described below). Elastic Beanstalk works well and is easy to set up. See `.github/workflows/deploy.yml` for an example GitHub Action that automates the deployment process.

### Automating tool metadata refresh (AWS)
Use the provided Lambda function and helper script to update the dynamic tool
metadata daily:

1. Package the Lambda code
   ```bash
   $  ./Agent2NotionServer/scripts/build_lambda_daily_tool_update.sh 
   ```

2. Run `./Agent2NotionServer/aws/setup_daily_tool_update.sh` to create the Lambda. Copy the LAMBDA_ARN in your `.env` file.

3. Run `./setup_daily_lambda_event.sh` to setup the Lambda to run every day.

4. (As needed) Update the function code to propagate any changes
   ```bash
   $ aws s3 cp Agent2NotionServer/scripts/lambda_daily_tool_update.zip \
         s3://${SCHEMA_REFRESH_CODE_BUCKET}/lambda/agent2notion-daily-tool-update.zip \
         --region us-east-1

   $ aws lambda update-function-code \
     --function-name agent2notion-daily-tool-update \
     --s3-bucket ${SCHEMA_REFRESH_CODE_BUCKET} \
     --s3-key lambda/agent2notion-daily-tool-update.zip \
     --region us-east-1
   ```

The Lambda will regenerate `notion_tools_data.json`, upload the JSON file to the S3 bucket
specified by `NOTION_TOOL_DATA_BUCKET`, and restart the environment defined in
`EB_ENVIRONMENT_NAME`.

You need to set the following environment variables for the Lambda to work correctly:
* NOTION_TOOL_DATA_BUCKET
* EB_ENVIRONMENT_NAME
* NOTION_TOKEN (stored as a secret with a SecretId of the same name)
* OPENAI_API_KEY (stored as a secret with a SecretId of the same name)

### Running the server locally
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
The `/search-notion` endpoint performs an LLM-powered search over your cached
workspace metadata. It returns matching page content and filtered database
results.

```bash
curl -X POST http://localhost:8000/search-notion \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "meeting notes"}'
```

---

## 🛠  Extending the Agent
**Expose more of your workspace**: simply share additional pages/databases with the integration token and rerun `generate_notion_tool_data.py`.
**Custom instructions** Update your `db_custom_instructions.json` file in S3 to provide the agent with more specific guidance on a given page. This file should be formatted as a simple JSON object, where the key is the Notion page or database ID, and the value is a string with the custom instructions.

---

## 🩺 Health Check
`GET /health` → `{ "status": "healthy" }`

---

## License
MIT © 2024
