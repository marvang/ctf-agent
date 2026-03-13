"""
Step 1: Parse reconnaissance command logs into structured service information.

Takes raw terminal output from recon tools (nmap, gobuster, etc.) and uses
an LLM to extract structured data about discovered services.
"""

from typing import Dict, Any
from src.web_search.llm_client import call_llm_json

RECON_PARSER_SYSTEM_PROMPT = """You are a cybersecurity reconnaissance analyst. Your job is to parse raw terminal command logs from reconnaissance tools and extract structured information about discovered services, software, and infrastructure.

You MUST respond with valid JSON only. No explanations or markdown outside the JSON.

Output format:
{
  "target_ip": "the target IP address",
  "services": [
    {
      "port": 80,
      "protocol": "tcp",
      "service_name": "http",
      "product": "Apache httpd",
      "version": "2.4.49",
      "extra_info": "any additional details like OS, modules, configs",
      "cpe": "cpe string if available"
    }
  ],
  "os_detection": {
    "os_name": "detected OS or null",
    "os_version": "version or null",
    "confidence": "high/medium/low"
  },
  "web_technologies": [
    {
      "name": "technology name (e.g. WordPress, PHP, jQuery)",
      "version": "version if known or null",
      "location": "where it was found (URL path, header, etc.)"
    }
  ],
  "interesting_paths": [
    {
      "path": "/admin",
      "status_code": 200,
      "notes": "any relevant observations"
    }
  ],
  "credentials_or_usernames": ["any discovered usernames or default creds"],
  "raw_observations": ["other notable findings that don't fit above categories"]
}

Rules:
- Extract EVERY service, version, and technology mentioned in the logs
- If a version number is visible, ALWAYS include it - this is critical for vulnerability research
- Include CPE strings if nmap provides them
- Be thorough - missing a service version could mean missing a critical vulnerability
- If information is not available for a field, use null or empty arrays
- Do NOT hallucinate information not present in the logs"""

RECON_PARSER_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "recon_results",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "target_ip": {"type": "string"},
                "services": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "port": {"type": "integer"},
                            "protocol": {"type": "string"},
                            "service_name": {"type": "string"},
                            "product": {"type": "string"},
                            "version": {"type": "string"},
                            "extra_info": {"type": "string"},
                            "cpe": {"type": "string"}
                        },
                        "required": ["port", "protocol", "service_name", "product", "version"],
                        "additionalProperties": False
                    }
                },
                "os_detection": {
                    "type": "object",
                    "properties": {
                        "os_name": {"type": "string"},
                        "os_version": {"type": "string"},
                        "confidence": {"type": "string"}
                    },
                    "required": ["os_name", "os_version", "confidence"],
                    "additionalProperties": False
                },
                "web_technologies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "version": {"type": "string"},
                            "location": {"type": "string"}
                        },
                        "required": ["name", "version", "location"],
                        "additionalProperties": False
                    }
                },
                "interesting_paths": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "status_code": {"type": "integer"},
                            "notes": {"type": "string"}
                        },
                        "required": ["path", "status_code", "notes"],
                        "additionalProperties": False
                    }
                },
                "credentials_or_usernames": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "raw_observations": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["target_ip", "services", "os_detection", "web_technologies",
                         "interesting_paths", "credentials_or_usernames", "raw_observations"],
            "additionalProperties": False
        }
    }
}


def parse_recon_logs(command_logs: str, model_name: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Parse raw reconnaissance command logs into structured service data.

    Args:
        command_logs: Raw terminal output from recon session
        model_name: OpenRouter model identifier

    Returns:
        Tuple of (structured_recon_data, usage_dict)
    """
    user_prompt = f"""Parse the following reconnaissance command logs and extract all service information, versions, technologies, and notable findings.

COMMAND LOGS:
{command_logs}"""

    return call_llm_json(
        system_prompt=RECON_PARSER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model_name=model_name,
        json_schema=RECON_PARSER_SCHEMA
    )
