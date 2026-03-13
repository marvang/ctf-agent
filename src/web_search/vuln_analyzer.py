"""
Step 4: Analyze search results to identify potential vulnerabilities.

Takes search results and uses an LLM to identify, prioritize, and summarize
vulnerabilities with actionable exploitation guidance.
"""

from typing import Dict, Any
from src.web_search.llm_client import call_llm_json

VULN_ANALYZER_SYSTEM_PROMPT = """You are a penetration testing vulnerability analyst. Given web search results from vulnerability research, analyze them and produce a structured vulnerability report.

You MUST respond with valid JSON only.

Output format:
{
  "vulnerabilities": [
    {
      "cve_id": "CVE-XXXX-XXXXX or null if no specific CVE",
      "title": "short vulnerability title",
      "affected_service": "service name and version",
      "severity": "critical|high|medium|low",
      "description": "what the vulnerability is",
      "exploitation_notes": "how this could be exploited in a CTF/pentest context",
      "exploit_available": true,
      "exploit_source": "URL or tool name for a known exploit, or null",
      "confidence": "confirmed|likely|possible"
    }
  ],
  "recommended_attack_path": [
    {
      "step": 1,
      "action": "what to do",
      "target": "which service/port",
      "rationale": "why this step"
    }
  ],
  "summary": "Brief overall assessment of the target's attack surface"
}

Analysis rules:
- Only include vulnerabilities that are RELEVANT to the specific versions found in recon
- Do NOT include vulnerabilities for different versions than what was discovered
- Prioritize RCE, auth bypass, and file read/write vulnerabilities
- For each vulnerability, note whether a public exploit exists
- The recommended_attack_path should order actions from most promising to least
- Be specific about exploit tools (searchsploit ID, Metasploit module, GitHub PoC URL)
- Mark confidence as 'confirmed' only if the exact version matches a known CVE
- If search results are sparse, say so honestly rather than speculating"""

VULN_ANALYZER_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "vulnerability_report",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "vulnerabilities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cve_id": {"type": "string"},
                            "title": {"type": "string"},
                            "affected_service": {"type": "string"},
                            "severity": {"type": "string"},
                            "description": {"type": "string"},
                            "exploitation_notes": {"type": "string"},
                            "exploit_available": {"type": "boolean"},
                            "exploit_source": {"type": "string"},
                            "confidence": {"type": "string"}
                        },
                        "required": ["cve_id", "title", "affected_service", "severity",
                                     "description", "exploitation_notes", "exploit_available",
                                     "exploit_source", "confidence"],
                        "additionalProperties": False
                    }
                },
                "recommended_attack_path": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "integer"},
                            "action": {"type": "string"},
                            "target": {"type": "string"},
                            "rationale": {"type": "string"}
                        },
                        "required": ["step", "action", "target", "rationale"],
                        "additionalProperties": False
                    }
                },
                "summary": {"type": "string"}
            },
            "required": ["vulnerabilities", "recommended_attack_path", "summary"],
            "additionalProperties": False
        }
    }
}


def analyze_vulnerabilities(recon_data: Dict[str, Any],
                            search_results: list,
                            model_name: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Analyze search results to identify and prioritize vulnerabilities.

    Args:
        recon_data: Original structured recon data (for context on exact versions)
        search_results: List of search result dicts from execute_searches
        model_name: OpenRouter model identifier

    Returns:
        Tuple of (vulnerability_report_dict, usage_dict)
    """
    import json

    user_prompt = f"""Analyze the following search results and identify potential vulnerabilities for the target.

RECON DATA (services and versions found on target):
{json.dumps(recon_data, indent=2)}

SEARCH RESULTS:
{json.dumps(search_results, indent=2)}

Identify all relevant vulnerabilities, prioritize them, and suggest an attack path."""

    return call_llm_json(
        system_prompt=VULN_ANALYZER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model_name=model_name,
        json_schema=VULN_ANALYZER_SCHEMA
    )
