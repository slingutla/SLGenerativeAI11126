# create a connection to your MCP server
transport = PythonStdioTransport("mcp_server_fastmcp.py")

async with Client(transport) as client:
    await run_agent("Give me a summary of the dataset", client)

# create a connection to your MCP server
transport = PythonStdioTransport("mcp_server_fastmcp.py")

async with Client(transport) as client:
    await run_agent("Give me a summary of the dataset", client)
    await run_agent("Show West region sales > 1500", client)