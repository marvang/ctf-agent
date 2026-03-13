"""
Web search pipeline orchestrator.

Ties together all 4 steps of the vulnerability research pipeline:
1. Parse recon logs → structured services
2. Generate search queries
3. Execute web searches
4. Analyze results for vulnerabilities
"""

import json
from typing import Dict, Any
from src.web_search.recon_parser import parse_recon_logs
from src.web_search.query_generator import generate_search_queries
from src.web_search.searcher import execute_searches
from src.web_search.vuln_analyzer import analyze_vulnerabilities


def run_web_search_pipeline(command_logs: str,
                            model_name: str,
                            max_results_per_query: int = 5,
                            search_delay: float = 1.0) -> Dict[str, Any]:
    """
    Run the full web search vulnerability research pipeline.

    Args:
        command_logs: Raw terminal output from reconnaissance session
        model_name: OpenRouter model identifier (e.g. "openai/gpt-4")
        max_results_per_query: Max search results per query
        search_delay: Seconds between search requests (rate limiting)

    Returns:
        Dict with keys:
            - recon_data: Structured recon information
            - queries: Generated search queries
            - search_results: Raw search results
            - vuln_report: Final vulnerability analysis
            - usage: Aggregated token usage across all LLM calls
    """
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Step 1: Parse recon logs
    print("[*] Step 1/4: Parsing reconnaissance logs...")
    recon_data, usage1 = parse_recon_logs(command_logs, model_name)
    _aggregate_usage(total_usage, usage1)

    services_found = len(recon_data.get("services", []))
    tech_found = len(recon_data.get("web_technologies", []))
    print(f"    Found {services_found} services, {tech_found} web technologies")

    # Step 2: Generate search queries
    print("[*] Step 2/4: Generating search queries...")
    queries, usage2 = generate_search_queries(recon_data, model_name)
    _aggregate_usage(total_usage, usage2)

    print(f"    Generated {len(queries)} search queries")

    # Step 3: Execute web searches
    print(f"[*] Step 3/4: Searching the web ({len(queries)} queries)...")
    search_results = execute_searches(
        queries,
        max_results_per_query=max_results_per_query,
        delay_between=search_delay
    )

    total_results = sum(len(r.get("results", [])) for r in search_results)
    print(f"    Collected {total_results} search results")

    # Step 4: Analyze for vulnerabilities
    print("[*] Step 4/4: Analyzing results for vulnerabilities...")
    vuln_report, usage3 = analyze_vulnerabilities(recon_data, search_results, model_name)
    _aggregate_usage(total_usage, usage3)

    vulns_found = len(vuln_report.get("vulnerabilities", []))
    print(f"    Identified {vulns_found} potential vulnerabilities")
    print("[+] Web search pipeline complete.")

    return {
        "recon_data": recon_data,
        "queries": queries,
        "search_results": search_results,
        "vuln_report": vuln_report,
        "usage": total_usage,
    }


def _aggregate_usage(total: Dict[str, int], new: Dict[str, Any]) -> None:
    """Add token counts from a new usage dict into the running total."""
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        total[key] += new.get(key, 0)
