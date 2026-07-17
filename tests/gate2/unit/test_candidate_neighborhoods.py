from datetime import datetime, timedelta, timezone
import inspect
from uuid import UUID

from research_workspace.application.services import candidate_detection
from research_workspace.application.services.candidate_detection import (
    CandidateNeighbor,
    CandidateNeighborhoodIndex,
    schedule_candidate_comparisons,
)


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _neighbor(
    number: int,
    *,
    seconds: int = 0,
    sha256: str | None = None,
    observations: tuple[UUID, ...] = (),
    papers: tuple[UUID, ...] = (),
    lineages: tuple[str, ...] = (),
) -> CandidateNeighbor:
    return CandidateNeighbor(
        snapshot_id=UUID(int=number),
        sha256=sha256 or f"{number:064x}",
        first_seen_at=NOW + timedelta(seconds=seconds),
        source_observation_ids=observations,
        active_paper_ids=papers,
        filename_lineage_keys=lineages,
    )


def test_neighborhood_limits_and_total_order_are_deterministic() -> None:
    observation_id = UUID(int=1000)
    paper_id = UUID(int=2000)
    target = _neighbor(
        100,
        observations=(observation_id,),
        papers=(paper_id,),
        lineages=("paper",),
    )
    records = (
        target,
        _neighbor(1, seconds=-1, observations=(observation_id,)),
        _neighbor(2, seconds=1, observations=(observation_id,)),
        _neighbor(3, seconds=2, observations=(observation_id,)),
        *(
            _neighbor(number, seconds=number - 10, papers=(paper_id,))
            for number in range(10, 17)
        ),
        *(
            _neighbor(number, seconds=number - 20, lineages=("paper",))
            for number in range(20, 27)
        ),
    )

    comparisons = schedule_candidate_comparisons(
        target, CandidateNeighborhoodIndex(records)
    )

    assert len(comparisons) == 12
    assert tuple(item.neighbor_snapshot_id for item in comparisons[:2]) == (
        UUID(int=1),
        UUID(int=2),
    )
    assert tuple(item.neighborhoods for item in comparisons[:2]) == (
        ("source_continuity",),
        ("source_continuity",),
    )
    assert len({item.neighbor_snapshot_id for item in comparisons}) == 12


def test_equal_distance_ties_use_snapshot_sha256() -> None:
    paper_id = UUID(int=3000)
    target = _neighbor(100, papers=(paper_id,))
    larger_id_smaller_sha = _neighbor(
        2, seconds=1, sha256="1" * 64, papers=(paper_id,)
    )
    smaller_id_larger_sha = _neighbor(
        1, seconds=-1, sha256="f" * 64, papers=(paper_id,)
    )

    comparisons = schedule_candidate_comparisons(
        target,
        CandidateNeighborhoodIndex(
            (target, smaller_id_larger_sha, larger_id_smaller_sha)
        ),
    )

    assert tuple(item.neighbor_snapshot_id for item in comparisons) == (
        larger_id_smaller_sha.snapshot_id,
        smaller_id_larger_sha.snapshot_id,
    )


def test_duplicate_neighbors_are_merged_across_neighborhoods() -> None:
    observation_id = UUID(int=4000)
    paper_id = UUID(int=5000)
    target = _neighbor(
        100,
        observations=(observation_id,),
        papers=(paper_id,),
        lineages=("paper",),
    )
    shared = _neighbor(
        1,
        seconds=1,
        observations=(observation_id,),
        papers=(paper_id,),
        lineages=("paper",),
    )

    comparisons = schedule_candidate_comparisons(
        target, CandidateNeighborhoodIndex((target, shared))
    )

    assert len(comparisons) == 1
    assert comparisons[0].neighborhoods == (
        "source_continuity",
        "paper_membership",
        "filename_lineage",
    )


def test_scheduler_excludes_same_snapshot_and_same_content() -> None:
    paper_id = UUID(int=6000)
    target = _neighbor(100, papers=(paper_id,))
    same_content = _neighbor(1, sha256=target.sha256, papers=(paper_id,))

    assert (
        schedule_candidate_comparisons(
            target, CandidateNeighborhoodIndex((target, same_content))
        )
        == ()
    )


def test_index_has_no_all_pairs_api_or_pair_materialization() -> None:
    public_names = {
        name
        for name in dir(CandidateNeighborhoodIndex)
        if not name.startswith("_")
    }
    source = inspect.getsource(candidate_detection)

    assert not {"all_pairs", "pairs", "combinations"} & public_names
    assert "itertools.combinations" not in source
    assert "for left in records for right in records" not in source
