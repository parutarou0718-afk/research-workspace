import pytest

from research_workspace.domain.versioning import (
    VersioningError,
    normalize_version_label,
)


def test_version_label_normalization_is_versioned_unicode_and_semantic() -> None:
    assert normalize_version_label("  Re\u0301V\t 2!  ") == "rév 2!"
    assert normalize_version_label("Final-2") == "final-2"


@pytest.mark.parametrize("label", ["", "   ", "x" * 201])
def test_version_label_display_length_is_bounded(label: str) -> None:
    with pytest.raises(VersioningError, match="INVALID_VERSION_LABEL"):
        normalize_version_label(label)
