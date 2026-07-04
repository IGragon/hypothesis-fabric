from __future__ import annotations

import logging
import sys

_CONFIGURED = False


_NOISY_LIBS = (
    "neo4j", "neo4j.pool", "neo4j.io",
    "httpx", "httpcore", "httpcore.http11", "httpcore.connection",
    "sentence_transformers", "sentence_transformers.util.file_io",
    "ddgs", "ddgs.ddgs",
    "openai", "openai._base_client",
    "primp",
    "urllib3", "urllib3.connectionpool",
    "httpbuilder",
    "asyncio",
)


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED

    fmt = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    if not _CONFIGURED:
        root.handlers.clear()
    if not any(getattr(h, "_hfabric_handler", False) for h in root.handlers):
        handler._hfabric_handler = True  # type: ignore[attr-defined]
        root.addHandler(handler)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)
    logging.getLogger("hfabric").setLevel(numeric_level)

    for lib in _NOISY_LIBS:
        logging.getLogger(lib).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_stage_logger(stage: str, run_id: str = "") -> logging.LoggerAdapter:
    logger = logging.getLogger(f"hfabric.{stage}")
    return logging.LoggerAdapter(logger, {"run_id": run_id})