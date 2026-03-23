"""Helpers for collision-resistant run identifiers."""

from __future__ import annotations

import uuid
from datetime import datetime


def generate_run_id(timestamp: str | None = None) -> str:
    """Return a timestamped run identifier with a short random suffix."""
    resolved_timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{resolved_timestamp}_{uuid.uuid4().hex[:8]}"
