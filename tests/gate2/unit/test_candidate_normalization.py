import unicodedata

import pytest

from research_workspace.application.services.candidate_detection import (
    DEFAULT_CANDIDATE_RULE_CONFIG,
    normalize_candidate_title,
    normalize_filename_lineage,
    rule_config_fingerprint,
)


def test_title_normalization_is_nfc_trim_fold_and_casefold() -> None:
    decomposed = unicodedata.normalize("NFD", "Résumé")
    assert normalize_candidate_title(f" \t{decomposed}\n  PAPER  ") == "résumé paper"
    assert normalize_candidate_title("Ａ  B") == "ａ b"


@pytest.mark.parametrize(
    ("filename", "lineage", "token"),
    (
        (" Study---Draft.docx ", "study", "draft"),
        ("study_rev2.PDF", "study", "rev2"),
        ("研究.修订稿3.pptx", "研究", "修订稿3"),
        ("meaningful.v2.notes.pdf", "meaningful v2 notes", None),
        ("final-results.pdf", "final results", None),
    ),
)
def test_filename_lineage_removes_only_final_extension_and_final_token(
    filename, lineage, token
) -> None:
    normalized = normalize_filename_lineage(filename)
    assert normalized.lineage_key == lineage
    assert normalized.version_token == token


def test_rule_config_fingerprint_is_default_expanded_canonical_and_closed() -> None:
    first = rule_config_fingerprint({})
    second = rule_config_fingerprint(
        dict(reversed(tuple(DEFAULT_CANDIDATE_RULE_CONFIG.items())))
    )
    assert first == second
    assert len(first) == 64
    with pytest.raises(ValueError, match="CANDIDATE_RULE_CONFIG_INVALID"):
        rule_config_fingerprint({"opaque_weight": 0.75})
