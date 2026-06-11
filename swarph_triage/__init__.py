"""swarph-triage — ranked-queue triage primitive.

Public API:

    from swarph_triage import open
    q = open(db_url, config=..., proposer_fn=...)
    q.ingest(fingerprint=..., severity=..., actionability=..., context=...)
    q.transition(fp_id, to_status=..., actor=..., note=...)
    q.list(limit=20)
    q.show(fp_id)

See README.md for the full surface.
"""

from swarph_triage._version import __version__
from swarph_triage.queue import TriageQueue, open  # noqa: F401
from swarph_triage.state_machine import Status, VALID_TRANSITIONS  # noqa: F401
from swarph_triage.config import DEFAULT_CONFIG, load_config  # noqa: F401

__all__ = [
    "__version__",
    "open",
    "TriageQueue",
    "Status",
    "VALID_TRANSITIONS",
    "DEFAULT_CONFIG",
    "load_config",
]
