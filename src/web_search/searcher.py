"""
Step 3: Execute web searches using DuckDuckGo HTML (no API key required).

Performs searches and returns raw result text for LLM analysis.
"""

import json
import re
import time
from html import unescape
from typing import Dict, Any, List
from urllib import request, parse
from urllib.error import HTTPError, URLError


def search_duckduckgo(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Search DuckDuckGo HTML and extract results.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        List of dicts with 'title', 'url', 'snippet' keys
    """
    encoded_query = parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    }

    req = request.Request(url, headers=headers)
    try:
        with request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError):
        return []

    results = []

    # Extract result blocks from DuckDuckGo HTML
    result_blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )

    for link, title, snippet in result_blocks[:max_results]:
        # DuckDuckGo wraps URLs in a redirect - extract the actual URL
        actual_url = link
        uddg_match = re.search(r'uddg=([^&]+)', link)
        if uddg_match:
            actual_url = parse.unquote(uddg_match.group(1))

        clean_title = re.sub(r'<[^>]+>', '', title).strip()
        clean_snippet = re.sub(r'<[^>]+>', '', snippet).strip()
        clean_title = unescape(clean_title)
        clean_snippet = unescape(clean_snippet)

        if clean_title:
            results.append({
                "title": clean_title,
                "url": actual_url,
                "snippet": clean_snippet,
            })

    return results


def execute_searches(queries: List[Dict[str, Any]],
                     max_results_per_query: int = 5,
                     delay_between: float = 1.0) -> List[Dict[str, Any]]:
    """
    Execute a batch of search queries and collect results.

    Args:
        queries: List of query dicts from query_generator (with 'query', 'target_service', etc.)
        max_results_per_query: Max results per individual search
        delay_between: Seconds to wait between searches (rate limiting)

    Returns:
        List of dicts, each containing the original query info plus 'results' list
    """
    search_results = []

    for i, query_info in enumerate(queries):
        query_text = query_info.get("query", "")
        if not query_text:
            continue

        results = search_duckduckgo(query_text, max_results=max_results_per_query)

        search_results.append({
            "query": query_text,
            "target_service": query_info.get("target_service", ""),
            "search_intent": query_info.get("search_intent", ""),
            "priority": query_info.get("priority", "medium"),
            "results": results,
        })

        # Rate limit to avoid getting blocked
        if i < len(queries) - 1:
            time.sleep(delay_between)

    return search_results
