from duckduckgo_search import DDGS
with DDGS() as ddsearch:
    print(list(ddsearch.text("latest trends in commercial real estate", max_results=5)))