from datetime import datetime, timedelta, timezone
from uuid import UUID

from research_workspace.application.services.candidate_detection import (
    CandidateNeighbor,
    CandidateNeighborhoodIndex,
    schedule_candidate_comparisons,
)


def test_ten_thousand_snapshots_produce_at_most_twelve_comparisons_each() -> None:
    first_seen = datetime(2026, 7, 17, tzinfo=timezone.utc)
    paper_id = UUID(int=20001)
    records = tuple(
        CandidateNeighbor(
            snapshot_id=UUID(int=index + 1),
            sha256=f"{index + 1:064x}",
            first_seen_at=first_seen + timedelta(seconds=index),
            source_observation_ids=(UUID(int=index // 20 + 30000),),
            active_paper_ids=(paper_id,),
            filename_lineage_keys=(f"lineage-{index // 100}",),
        )
        for index in range(10_000)
    )
    index = CandidateNeighborhoodIndex(records)

    total = sum(
        len(schedule_candidate_comparisons(record, index))
        for record in records
    )

    assert total <= 120_000
    assert all(
        len(schedule_candidate_comparisons(record, index)) <= 12
        for record in records
    )
