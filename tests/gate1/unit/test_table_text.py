from __future__ import annotations

from research_workspace.infrastructure.parsers.table_text import (
    TABLE_TEXT_VERSION,
    escape_table_tsv,
)


def test_tsv_encoder_has_locked_version() -> None:
    assert TABLE_TEXT_VERSION == "tsv-escaped-1"


def test_tsv_escape_order_is_unambiguous_and_reversible() -> None:
    table = [[r"a\b", "x\ty", "z\r\nw", r"literal\t"]]
    encoded = escape_table_tsv(table)
    assert encoded == "\t".join([r"a\\b", r"x\ty", r"z\r\nw", r"literal\\t"])

    cells = encoded.split("\t")
    assert cells == [r"a\\b", r"x\ty", r"z\r\nw", r"literal\\t"]

    def decode(cell: str) -> str:
        result: list[str] = []
        index = 0
        escapes = {"\\": "\\", "t": "\t", "n": "\n", "r": "\r"}
        while index < len(cell):
            if cell[index] == "\\":
                index += 1
                result.append(escapes[cell[index]])
            else:
                result.append(cell[index])
            index += 1
        return "".join(result)

    assert [[decode(cell) for cell in cells]] == table


def test_tsv_uses_real_tab_and_lf_only_as_structural_separators() -> None:
    assert escape_table_tsv([["a", "b"], ["c", "d"]]) == "a\tb\nc\td"
    assert escape_table_tsv([["a\rb", "c\nd", "e\tf", "g\\h"]]) == "\t".join(
        [r"a\rb", r"c\nd", r"e\tf", r"g\\h"]
    )


def test_empty_table_and_empty_cells_are_deterministic() -> None:
    assert escape_table_tsv([]) == ""
    assert escape_table_tsv([["", ""]]) == "\t"
