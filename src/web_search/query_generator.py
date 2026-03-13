"""
Step 2: Generate targeted search queries from structured recon data.

Takes the structured service/version JSON from the recon parser and generates
specific search queries to find known vulnerabilities and exploits.
"""

from typing import Dict, Any, List
from src.web_search.llm_client import call_llm_json

QUERY_GEN_SYSTEM_PROMPT = """You are a cybersecurity vulnerability researcher. Given structured reconnaissance data about a target's services and technologies, generate targeted web search queries to find known vulnerabilities, exploits, and attack techniques.

You MUST respond with valid JSON only.

Output format:
{
  "queries": [
    {
      "query": "the search query string",
      "target_service": "which service/technology this query targets",
      "search_intent": "cve|exploit|misconfiguration|default_creds|technique",
      "priority": "high|medium|low"
    }
  ]
}

Query generation rules:
- For each service with a known version, generate:
  1. A CVE search: "<product> <version> CVE vulnerability"
  2. An exploit search: "<product> <version> exploit"
  3. If version is recent, also search for the product name with "RCE" or "auth bypass"
- For web technologies (WordPress, Drupal, etc.), search for plugin/theme vulns
- For interesting paths (/admin, /api, etc.), search for known bypasses
- For detected OS versions, search for privilege escalation techniques
- Prioritize queries for services with known version numbers (these are most actionable)
- Include "site:exploit-db.com" or "site:github.com" variants for high-priority services
- Generate 5-20 queries depending on the number of services found
- Order by priority: services with exact versions first, then general technique queries"""

QUERY_GEN_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "search_queries",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "target_service": {"type": "string"},
                            "search_intent": {"type": "string"},
                            "priority": {"type": "string"}
                        },
                        "required": ["query", "target_service", "search_intent", "priority"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["queries"],
            "additionalProperties": False
        }
    }
}


def generate_search_queries(recon_data: Dict[str, Any],
                            model_name: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Generate search queries from structured recon data.

    Args:
        recon_data: Structured recon output from parse_recon_logs
        model_name: OpenRouter model identifier

    Returns:
        Tuple of (list_of_query_dicts, usage_dict)
    """
    import json
    user_prompt = f"""Generate targeted vulnerability search queries for the following reconnaissance data:

RECON DATA:
{json.dumps(recon_data, indent=2)}"""

    result, usage = call_llm_json(
        system_prompt=QUERY_GEN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model_name=model_name,
        json_schema=QUERY_GEN_SCHEMA
    )

    queries = result.get("queries", [])
    return queries, usage
