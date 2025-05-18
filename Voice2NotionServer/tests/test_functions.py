import os
import asyncio
from dotenv import load_dotenv
from notion_client import AsyncClient

load_dotenv()

async def test_database_schema():
    """Test the get_database_schema function"""
    database_id = os.getenv("NOTION_PAGE_ID")
    if not database_id:
        print("Error: NOTION_PAGE_ID not found in environment variables")
        return
    
    notion = AsyncClient(auth=os.getenv("NOTION_TOKEN"))
    try:
        database = await notion.databases.retrieve(database_id=database_id)
        print("\nDatabase Schema Test:")
        print("-------------------")
        print(f"Database Name: {database.get('title', [{}])[0].get('plain_text', 'Untitled Database')}")
        print("\nSchema:")
        for prop_name, prop_info in database.get("properties", {}).items():
            print(f"\n{prop_name}:")
            print(f"  Type: {prop_info.get('type')}")
            if prop_info.get("type") == "select":
                options = prop_info.get("select", {}).get("options", [])
                print(f"  Options: {[opt['name'] for opt in options]}")
            elif prop_info.get("type") == "multi_select":
                options = prop_info.get("multi_select", {}).get("options", [])
                print(f"  Options: {[opt['name'] for opt in options]}")
            elif prop_info.get("type") == "relation":
                related_database = prop_info.get("relation", {}).get("database_id")
                print(f"  Related Database: {related_database}")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        await notion.aclose()

async def test_create_entry():
    """Test the create_database_entry function"""
    database_id = os.getenv("NOTION_PAGE_ID")
    if not database_id:
        print("Error: NOTION_PAGE_ID not found in environment variables")
        return
    
    notion = AsyncClient(auth=os.getenv("NOTION_TOKEN"))
    test_properties = {
        "Name": {"title": [{"text": {"content": "Test Entry"}}]},
        "Status": {"status": {"name": "Not started"}}
    }
    try:
        new_page = await notion.pages.create(
            parent={"database_id": database_id},
            properties=test_properties
        )
        print("\nCreate Entry Test:")
        print("----------------")
        print(f"Created page with ID: {new_page['id']}")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        await notion.aclose()

if __name__ == "__main__":
    print("Testing Notion Functions...")
    asyncio.run(test_database_schema())
    asyncio.run(test_create_entry()) 
