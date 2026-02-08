
from fastmcp import Client
from fastmcp.client import PythonStdioTransport
import asyncio

async def main():
    # Create a client using the PythonStdioTransport
    # Create a loop to run the client

    transport = PythonStdioTransport("mcp_server_fastmcp.py")
    
    # client = Client(transport)

    async with Client(transport) as client:
        tools = await client.list_tools()
        print("Tools:", [t.name for t in tools])
        await run_agent("Give me a summary of the dataset", client)

# Simulate a Simple Host Agent
# Let's simulate a rule-based 'AI agent' that decides whether to use summarize or query based on user text.

def decide_tool(text: str):
    text = text.lower()
    if "summarize" in text or "overview" in text:
        return "summarize", {}
    if "west" in text:
        return "query", {"expr": "region == 'West' and sales > 1500"}
    return "summarize", {}

async def run_agent(user_input, client):
    tool, params = decide_tool(user_input) #"summarize", {}
    #tool = "summarize"
    #params = {}
    print(f"Agent decided to use '{tool}'")

    # API for fastmcp 2.12.5
    result = await client.call_tool(tool, params)
    # result = await client.call_tool("query", params)

    print("Result:", result, "\n")



# if __name__ == "__main__":
    # asyncio.run(main())

    transport = PythonStdioTransport("mcp_server_fastmcp.py")

    async with Client(transport) as client:
        await run_agent("Give me a summary of the dataset", client)

    print("Result:", result, "\n")