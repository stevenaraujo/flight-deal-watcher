"""Zentrales Logging-Setup. Keine Secrets werden je geloggt."""
from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Verhindert, dass Request-URLs mit potenziellen Query-Secrets zu ausführlich geloggt werden
    logging.getLogger("urllib3").setLevel(logging.WARNING)
