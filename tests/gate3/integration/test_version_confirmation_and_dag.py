from datetime import datetime, timezone
from uuid import uuid4

import pytest

from research_workspace.application.services.relation_graph import (
    VersionEdge,
    VersionGraphError,
    create_successor_relation,
)
from research_workspace.domain.versioning import PaperVersionRecord


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _version(paper_id=None, *, active=True) -> PaperVersionRecord:
    paper_id = paper_id or uuid4()
    return PaperVersionRecord(
        uuid4(), paper_id, uuid4(), None, "v1", "v1",
        "active" if active else "retracted", 1, NOW, uuid4(), NOW, uuid4(),
        None if active else NOW, None if active else uuid4(),
    )


def test_edge_direction_is_later_source_to_earlier_target() -> None:
    paper = uuid4()
    earlier, later = _version(paper), _version(paper)
    mutation = create_successor_relation(uuid4(), later, earlier, (), uuid4(), NOW)
    assert mutation.entity_type == "EntityRelation"
    assert str(later.id).encode() in mutation.after_snapshot
    assert str(earlier.id).encode() in mutation.after_snapshot
    assert b'"relation_type":"version_successor_of"' in mutation.after_snapshot


@pytest.mark.parametrize("case", ["self", "cross-paper", "inactive", "duplicate"])
def test_invalid_version_edges_are_rejected(case: str) -> None:
    paper = uuid4()
    earlier, later = _version(paper), _version(paper)
    edges = ()
    if case == "self":
        later = earlier
    elif case == "cross-paper":
        later = _version()
    elif case == "inactive":
        later = _version(paper, active=False)
    elif case == "duplicate":
        edges = (VersionEdge(uuid4(), paper, later.id, earlier.id),)
    with pytest.raises(VersionGraphError):
        create_successor_relation(uuid4(), later, earlier, edges, uuid4(), NOW)


def test_per_paper_dag_accepts_branch_merge_and_rejects_cycle() -> None:
    paper = uuid4()
    a, b, c, d = (_version(paper) for _ in range(4))
    edges = (
        VersionEdge(uuid4(), paper, b.id, a.id),
        VersionEdge(uuid4(), paper, c.id, a.id),
        VersionEdge(uuid4(), paper, d.id, b.id),
        VersionEdge(uuid4(), paper, d.id, c.id),
    )
    create_successor_relation(uuid4(), d, c, edges[:-1], uuid4(), NOW)
    with pytest.raises(VersionGraphError, match="VERSION_GRAPH_CYCLE"):
        create_successor_relation(uuid4(), a, d, edges, uuid4(), NOW)
