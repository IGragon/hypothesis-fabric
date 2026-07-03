from __future__ import annotations

import io
import logging

from hfabric.obs.logging import configure_logging, get_stage_logger


class TestConfigureLogging:
    def test_sets_root_level_info_by_default(self) -> None:
        configure_logging("INFO")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_debug_sets_hfabric_to_debug(self) -> None:
        configure_logging("DEBUG")
        hfabric_logger = logging.getLogger("hfabric")
        assert hfabric_logger.level == logging.DEBUG

    def test_adds_stream_handler(self) -> None:
        configure_logging("INFO")
        root = logging.getLogger()
        handlers = root.handlers
        assert any(isinstance(h, logging.StreamHandler) for h in handlers)

    def test_handler_has_correct_format(self) -> None:
        configure_logging("INFO")
        root = logging.getLogger()
        stream_handlers = [
            h for h in root.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) >= 1
        fmt = stream_handlers[0].formatter
        assert fmt is not None
        assert fmt._fmt == (
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
        )

    def test_invalid_level_falls_back_to_info(self) -> None:
        configure_logging("NONEXISTENT")
        root = logging.getLogger()
        assert root.level == logging.INFO


class TestGetStageLogger:
    def test_logger_name_includes_stage(self) -> None:
        logger = get_stage_logger("generate", "run-1")
        assert logger.logger.name == "hfabric.generate"

    def test_logger_is_adapter_with_run_id(self) -> None:
        logger = get_stage_logger("retrieve", "run-42")
        assert hasattr(logger, "extra")
        assert logger.extra == {"run_id": "run-42"}

    def test_log_messages_include_run_id(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(run_id)s %(message)s"))

        logger = get_stage_logger("test", "r-99")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        logger.info("hello")
        logger.logger.removeHandler(handler)

        output = stream.getvalue()
        assert "r-99" in output
        assert "hello" in output
