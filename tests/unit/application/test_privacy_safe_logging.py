import logging

from research_workspace.infrastructure.logging.configure_logging import configure_logging


def test_logs_redact_sensitive_fields(tmp_path):
    logger = configure_logging(tmp_path, "DEBUG", logger_name="privacy-test")
    logger.error("failure", extra={"paper_text": "SECRET", "api_key": "TOKEN", "category": "config"})

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "SECRET" not in text
    assert "TOKEN" not in text
    assert "config" in text
    assert "[REDACTED]" in text


def test_exception_stack_is_kept_without_sensitive_exception_values(tmp_path):
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-exception")

    try:
        raise RuntimeError("SECRET paper body")
    except RuntimeError:
        logger.exception("processing failed", extra={"paper_text": "SECRET paper body"})

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "Traceback" in text
    assert "RuntimeError" in text
    assert "SECRET paper body" not in text


def test_configured_log_level_is_enforced(tmp_path):
    logger = configure_logging(tmp_path, "WARNING", logger_name="privacy-level")
    logger.info("not-recorded")
    logger.warning("recorded")

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "not-recorded" not in text
    assert "recorded" in text


def test_nested_sensitive_context_is_redacted_without_losing_safe_context(tmp_path):
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-nested")
    logger.error(
        "configuration failed",
        extra={"technical_context": {"api_key": "NESTED-TOKEN", "operation": "save"}},
    )

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "NESTED-TOKEN" not in text
    assert '"operation": "save"' in text
