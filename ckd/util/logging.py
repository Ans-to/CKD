from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: str | int = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)-22s | %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
