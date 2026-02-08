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