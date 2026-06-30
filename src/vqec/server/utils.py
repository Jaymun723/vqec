from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    """Timezone-naive UTC datetime (matches legacy server)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def compute_config_hash(obj: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON (compatible with legacy server)."""
    encoded = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
