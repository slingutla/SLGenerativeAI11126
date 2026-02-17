from fastmcp import FastMCP
from duckduckgo_search import DDGS

mcp = FastMCP("codex-websearch")

@mcp.tool()
def search_web(query: str, max_results: int = 5) -> dict:
    """
    Search the internet using DuckDuckGo and return top results.

    Args:
        query: search query
        max_results: number of results to return
    """
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": r.get("title"),
                    "url": r.get("href"),
                    "snippet": r.get("body"),
                }
            )
    return {"query": query, "count": len(results), "results": results}

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8765)
