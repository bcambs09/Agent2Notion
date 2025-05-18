import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timedelta
from notion_agent import chain
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

load_dotenv()


async def test_agent():
    """Test the LangGraph agent with various task descriptions"""
    test_cases = [
        "Plan a dinner at sur barra nikkei with a High priority and a due date of April"
    ]

    print("\nTesting LangGraph Agent:")
    print("----------------------")

    for test_input in test_cases:
        print(f"\nTest Case: {test_input}")
        try:
            # Initialize the state
            state = {
                "messages": [HumanMessage(content=test_input)],
            }
            
            # Run the agent
            async for chunk in chain.astream(state, stream_mode="values"):
                chunk["messages"][-1].pretty_print()
            
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            print(f"Error type: {type(e)}")

if __name__ == "__main__":
    print("Testing Notion Integration and LangGraph Agent...")
    asyncio.run(test_agent())