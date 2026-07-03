from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    fmt = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    if level.upper() == "DEBUG":
        logging.getLogger("hfabric").setLevel(logging.DEBUG)


def get_stage_logger(stage: str, run_id: str) -> logging.Logger:
    logger = logging.getLogger(f"hfabric.{stage}")
    return logging.LoggerAdapter(logger, {"run_id": run_id})
