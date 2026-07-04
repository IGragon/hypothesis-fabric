from __future__ import annotations

import re

REDACTED_MARKER = "[REDACTED]"
MAX_TEXT_LENGTH = 100

_SOURCE_PATTERNS = [
    re.compile(r"report-\d+", re.IGNORECASE),
    re.compile(r"patent-\w+", re.IGNORECASE),
    re.compile(r"doc[-_]?\d+", re.IGNORECASE),
]


def redact_text(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    if not text and not isinstance(text, str):
        return text
    if not isinstance(text, str):
        return text

    redacted = text
    for pattern in _SOURCE_PATTERNS:
        redacted = pattern.sub(REDACTED_MARKER, redacted)

    if len(redacted) > max_length:
        return REDACTED_MARKER
    return redacted


def redact_trace(record: dict | object) -> dict:
    redacted: dict = {}
    fields_to_redact = {"text", "content", "payload", "description", "claim", "mechanism", "evidence"}

    if isinstance(record, dict):
        for key, value in record.items():
            if key.lower() in fields_to_redact:
                redacted[key] = redact_text(str(value)) if value else value
            elif key.lower().endswith("_id") or key.lower().endswith("_ref"):
                redacted[key] = value
            else:
                redacted[key] = value
    else:
        for key in dir(record):
            if key.startswith("_") or key.startswith("model_"):
                continue
            value = getattr(record, key, None)
            if key.lower() in fields_to_redact:
                setattr(record, key, redact_text(str(value)) if value else value)
        return record

    return redacted


def redact_log_message(record: str) -> str:
    for pattern in _SOURCE_PATTERNS:
        record = pattern.sub(REDACTED_MARKER, record)
    return record
