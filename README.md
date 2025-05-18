# Voice2Notion

A voice-to-Notion application that allows you to create Notion pages using voice input. The project consists of a Python server that processes the input and updates Notion using LangGraph and OpenAI.

## Project Structure

```
.
└── Voice2NotionServer/    # Python FastAPI server
```

## Setup

### Server Setup
1. Navigate to the `Voice2NotionServer` directory
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file with the following variables:
   ```
   OPENAI_API_KEY=your_openai_api_key
   NOTION_TOKEN=your_notion_integration_token
   NOTION_PAGE_ID=your_notion_page_id
   NOTION_MOVIE_DATABASE_ID=your_movie_database_id
   ```
5. Run the server:
   ```bash
   uvicorn main:app --reload
   ```
