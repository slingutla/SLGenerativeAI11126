import asyncio
import sys

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )
from fastmcp import FastMCP
from duckduckgo_search import DDGS
import json

from googlesearch import search


mcp = FastMCP("beginner-websearch")

@mcp.tool()
def search_web(query: str, max_results: int = 5) -> dict:
    """
    Search the internet using DuckDuckGo and return top results.

    Args:
        query: search query
        max_results: number of results to return
    """
    # results = []
    # with DDGS() as ddgs:
    #     for r in ddgs.text(query, max_results=max_results):
    #         results.append(
    #             {
    #                 "title": r.get("title"),
    #                 "url": r.get("href"),
    #                 "snippet": r.get("body"),
    #             }
    #         )

    # return {
    #     "query": query,
    #     "count": len(results),
    #     "results": results,
    # }

    try:
        results = []
        with search() as google_search:
            # Fetch search results
            ddgs_gen = google_search.text(query,region="us-en",safesearch="moderate",max_results=max_results)
            for r in ddgs_gen:
                results.append({
                    "title": r.get("title"),
                    "href": r.get("href"),
                    "body": r.get("body")
                })
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "results": []
        }

    return {
        "status": "success",
        "query": query,
        "count": len(results),
        "results": results
    }

if __name__ == "__main__":
    # mcp.run()
    mcp.run(transport="http", host="127.0.0.1", port=8765)
