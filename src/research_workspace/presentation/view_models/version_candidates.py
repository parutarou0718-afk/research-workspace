"""Pure display helpers for immutable candidate projections."""

import hashlib


def candidate_update_marker(candidate) -> str:
    payload = b"\x00".join(
        (
            str(candidate.row_version).encode(),
            candidate.status.encode(),
            candidate.direction_rationale_json,
            candidate.signals_json,
        )
    )
    return hashlib.sha256(payload).hexdigest()
