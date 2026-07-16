import pytest


@pytest.mark.parametrize(
    "state,label",
    [
        ("searchable", "已导入，可检索文本"),
        ("zero_text", "已导入，无可提取文本，需要 OCR"),
        ("parse_failed", "已导入，解析失败"),
        ("password_required", "已导入，需要密码"),
    ],
)
def test_status_vocabulary_is_exact_and_closed(state, label) -> None:
    from research_workspace.presentation.view_models.imports import localized_parse_status

    assert localized_parse_status(state) == label


def test_unknown_status_is_not_rendered_as_raw_enum() -> None:
    from research_workspace.presentation.view_models.imports import localized_parse_status

    with pytest.raises(ValueError, match="UNKNOWN_IMPORT_STATUS"):
        localized_parse_status("running")


def test_import_query_maps_terminal_database_facts_to_the_four_ui_states() -> None:
    from research_workspace.application.queries.get_imports import GetImports, ImportReadRecord

    query = GetImports(
        lambda: (
            ImportReadRecord("text.pdf", "succeeded", None, 2),
            ImportReadRecord("scan.pdf", "succeeded", None, 0),
            ImportReadRecord("broken.pdf", "failed", "PDF_CORRUPT", None),
            ImportReadRecord(
                "locked.pdf", "failed", "PDF_PASSWORD_REQUIRED", None
            ),
        )
    )

    assert tuple(row.status for row in query.execute().rows) == (
        "已导入，可检索文本",
        "已导入，无可提取文本，需要 OCR",
        "已导入，解析失败",
        "已导入，需要密码",
    )


def test_import_query_rejects_nonterminal_status_instead_of_mislabeling_it() -> None:
    from research_workspace.application.queries.get_imports import GetImports, ImportReadRecord

    query = GetImports(lambda: (ImportReadRecord("pending.pdf", "pending", None, None),))

    with pytest.raises(ValueError, match="UNKNOWN_IMPORT_STATUS"):
        query.execute()
