import io
import logging
from collections import namedtuple

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


def test_arbitrary_direct_messages_and_formatting_arguments_are_never_rendered(tmp_path):
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-direct")
    logger.error("PAPER-BODY-SECRET")
    logger.error("failed: %s", "MODEL-INPUT-SECRET")
    logger.error("ONEWORDSECRET")

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "PAPER-BODY-SECRET" not in text
    assert "MODEL-INPUT-SECRET" not in text
    assert "ONEWORDSECRET" not in text
    assert text.count("unexpected_error") == 3


def test_allowlisted_failure_category_and_safe_context_are_retained(tmp_path):
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-safe-category")
    logger.error(
        "failure",
        extra={
            "error_code": "CONFIG_SAVE_FAILED",
            "component": "config_store",
            "operation": "save",
            "retryable": False,
            "status": "failed",
            "count": 2,
            "attempt": 1,
        },
    )

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert " failure " in text
    assert "CONFIG_SAVE_FAILED" in text
    assert "config_store" in text
    assert '"count": 2' in text


def test_secret_aliases_unknown_fields_and_opaque_objects_are_not_rendered(tmp_path):
    class Opaque:
        def __str__(self):
            return "OPAQUE-SECRET"

    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-aliases")
    logger.error(
        "failure",
        extra={
            "access_token": "ACCESS-SECRET",
            "refreshToken": "REFRESH-SECRET",
            "client_secret": "CLIENT-SECRET",
            "paper_content": "PAPER-SECRET",
            "opaque": Opaque(),
            "technical_context": {
                "operation": "validate",
                "apiKey": "API-SECRET",
                "unknown": "UNKNOWN-SECRET",
                "region": {"name": "Tokyo", "zone": "1", "token": "REGION-SECRET"},
            },
        },
    )

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    for secret in (
        "ACCESS-SECRET", "REFRESH-SECRET", "CLIENT-SECRET", "PAPER-SECRET",
        "OPAQUE-SECRET", "API-SECRET", "UNKNOWN-SECRET", "REGION-SECRET",
    ):
        assert secret not in text
    assert "validate" in text
    assert "Tokyo" in text


def test_configured_logger_does_not_propagate_to_root_handlers(tmp_path):
    stream = io.StringIO()
    root_handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(root_handler)
    try:
        logger = configure_logging(tmp_path, "INFO", logger_name="privacy-root")
        logger.error("failure")
    finally:
        root.removeHandler(root_handler)

    assert stream.getvalue() == ""


def test_repeated_configuration_replaces_handler_instead_of_duplicating_output(tmp_path):
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-repeat")
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-repeat")
    logger.error("failure")

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert len(logger.handlers) == 1
    assert text.count(" failure") == 1


def test_named_tuple_context_is_normalized_to_json_array(tmp_path):
    Region = namedtuple("Region", "name zone")
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-tuple")
    logger.error("failure", extra={"region": Region("Tokyo", "1")})

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert '"region": ["Tokyo", "1"]' in text


def test_unknown_dynamic_context_key_is_not_rendered(tmp_path):
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-dynamic-key")
    logger.error("failure", extra={"SECRET-DYNAMIC-KEY": "SECRET-VALUE"})

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "SECRET-DYNAMIC-KEY" not in text
    assert "SECRET-VALUE" not in text


def test_tuple_under_safe_context_key_is_normalized_to_json_array(tmp_path):
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-safe-tuple")
    logger.error("failure", extra={"category": ("config", "save")})

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert '"category": ["config", "save"]' in text


def test_foundation_seed_template_maps_to_safe_category_without_rendering_argument(tmp_path):
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-seed")
    logger.info("Foundation seed manifest initialized: %s", "SECRET-SEED-ARGUMENT")

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "foundation_seed_initialized" in text
    assert "SECRET-SEED-ARGUMENT" not in text
    assert "Foundation seed manifest initialized" not in text


def test_self_referential_mapping_is_redacted_without_dropping_log(tmp_path):
    context = {"operation": "save"}
    context["technical_context"] = context
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-map-cycle")

    logger.error("failure", extra={"technical_context": context})

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "failure" in text
    assert "save" in text
    assert "[REDACTED]" in text


def test_self_referential_sequence_is_redacted_without_dropping_log(tmp_path):
    context = ["config"]
    context.append(context)
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-sequence-cycle")

    logger.error("failure", extra={"category": context})

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "failure" in text
    assert "config" in text
    assert "[REDACTED]" in text


def test_overly_deep_safe_context_is_redacted_without_dropping_log(tmp_path):
    context = ["leaf"]
    for _ in range(32):
        context = [context]
    logger = configure_logging(tmp_path, "INFO", logger_name="privacy-depth")

    logger.error("failure", extra={"category": context})

    text = (tmp_path / "research_workspace.log").read_text(encoding="utf-8")
    assert "failure" in text
    assert "[REDACTED]" in text
