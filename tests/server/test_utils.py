import hashlib
import json

from vqec.server.utils import compute_config_hash


def test_compute_config_hash_matches_legacy_format():
    payload = {"name": "test", "circuit": {"type": "x", "params": {"distance": 3}}}
    legacy = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert compute_config_hash(payload) == legacy
