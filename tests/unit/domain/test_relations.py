import itertools

import pytest

from research_workspace.domain.enums import RelationEntityType, RelationType
from research_workspace.domain.relations import (
    normalize_relation_endpoints,
    relation_key,
    validate_confirmation_transition,
    validate_relation_endpoints,
    validate_relation_provenance,
    would_create_relation_cycle,
)


IDEA_A = "00000000-0000-0000-0000-000000000001"
NOTE_B = "00000000-0000-0000-0000-000000000002"


ALLOWED = {
    "belongs_to": {("Note", "Paper"), ("SourceDocument", "Paper"), ("Submission", "Paper")},
    "derived_from": set(itertools.product(
        ("Idea", "Note", "PaperVersion"), ("SourceDocument", "Idea", "Note")
    )),
    "version_of": {("PaperVersion", "Paper")},
    "used_in": {("Idea", "Paper"), ("Idea", "PaperVersion")},
    "deleted_from": {("Idea", "PaperVersion")},
    "supports": set(itertools.product(
        ("Idea", "Note", "SourceDocument", "EvidenceRef"),
        ("Paper", "Idea", "Note", "Submission"),
    )),
    "contradicts": set(itertools.product(
        ("Idea", "Note", "SourceDocument"), repeat=2
    )),
    "extends": {("Paper", "Paper"), ("Idea", "Idea"), ("Note", "Note")},
    "related_to": set(itertools.product(
        ("Paper", "PaperVersion", "Idea", "Note", "SourceDocument", "Submission",
         "Conference", "Grant", "EvidenceRef"), repeat=2
    )),
    "presented_at": {("Paper", "Conference"), ("PaperVersion", "Conference")},
    "submitted_as": {("PaperVersion", "Submission")},
    "reviewed_by": {("Submission", "SourceDocument")},
    "suggested_for": {("Idea", "Paper")},
    "split_from": {("Paper", "Paper")},
    "merged_from": {("Paper", "Paper")},
}


def test_relation_enums_are_exactly_the_closed_approved_sets():
    assert {item.value for item in RelationType} == set(ALLOWED)
    assert {item.value for item in RelationEntityType} == {
        "Paper", "PaperVersion", "Idea", "Note", "SourceDocument", "Submission",
        "Conference", "Grant", "EvidenceRef",
    }


@pytest.mark.parametrize(
    ("relation_type", "source_type", "target_type"),
    [(relation, source, target) for relation, pairs in ALLOWED.items() for source, target in pairs],
)
def test_every_approved_endpoint_pair_is_accepted(relation_type, source_type, target_type):
    assert validate_relation_endpoints(
        relation_type, source_type, f"{source_type}-1", target_type, f"{target_type}-2"
    ) == ()


@pytest.mark.parametrize("relation_type", sorted(ALLOWED))
def test_each_relation_rejects_an_unapproved_endpoint_pair(relation_type):
    all_types = {item.value for item in RelationEntityType}
    invalid = ("Task", "Paper") if relation_type == "related_to" else next(
        pair for pair in itertools.product(all_types, repeat=2)
        if pair not in ALLOWED[relation_type]
    )
    assert validate_relation_endpoints(
        relation_type, invalid[0], "source", invalid[1], "target"
    ) == (f"{invalid[0]} -> {invalid[1]} is not allowed for {relation_type}",)


def test_symmetric_relation_has_one_canonical_key():
    forward = relation_key("contradicts", "Idea", IDEA_A, "Note", NOTE_B)
    reverse = relation_key("contradicts", "Note", NOTE_B, "Idea", IDEA_A)
    assert forward == reverse


def test_related_to_is_symmetric_but_directed_relations_retain_semantic_order():
    assert normalize_relation_endpoints("related_to", "Paper", "b", "Idea", "a") == (
        "Idea", "a", "Paper", "b"
    )
    assert normalize_relation_endpoints("supports", "Paper", "b", "Idea", "a") == (
        "Paper", "b", "Idea", "a"
    )


def test_all_relations_reject_a_self_link():
    for relation_type in ALLOWED:
        assert validate_relation_endpoints(
            relation_type, "Idea", IDEA_A, "Idea", IDEA_A
        ) == ("relation cannot target itself",)


def test_agent_relation_must_start_as_candidate():
    errors = validate_confirmation_transition(
        actor_type="agent", old_state=None, new_state="confirmed"
    )
    assert errors == ("agent-created relation must start as candidate",)


def test_confirmation_transitions_are_user_only_and_rejected_requires_explicit_reconsideration():
    assert validate_confirmation_transition("user", "candidate", "confirmed") == ()
    assert validate_confirmation_transition("agent", "candidate", "confirmed") == (
        "only a user may confirm or reject a candidate relation",
    )
    assert validate_confirmation_transition("user", "rejected", "candidate") == (
        "rejected relation requires explicit reconsideration",
    )
    assert validate_confirmation_transition(
        "user", "rejected", "candidate", reconsider=True
    ) == ()


def test_non_manual_first_observations_start_as_candidates():
    for provenance in ("rule", "import", "ai"):
        assert validate_confirmation_transition(
            "user", None, "confirmed", provenance_type=provenance
        ) == (f"{provenance}-created relation must start as candidate",)
    assert validate_confirmation_transition(
        "user", None, "confirmed", provenance_type="manual"
    ) == ()


def test_import_and_ai_provenance_require_exact_supporting_fields():
    base = dict(confidence=0.7, origin_task_id="task", evidence_ref_id="evidence")
    assert validate_relation_provenance("import", **base) == ()
    assert validate_relation_provenance("ai", **base, provider_id="provider", model_id="model") == ()
    assert validate_relation_provenance("import") == (
        "confidence is required for import provenance",
        "origin_task_id is required for import provenance",
        "evidence_ref_id is required for import provenance",
    )
    assert validate_relation_provenance("ai") == (
        "confidence is required for ai provenance",
        "origin_task_id is required for ai provenance",
        "evidence_ref_id is required for ai provenance",
        "provider_id is required for ai provenance",
        "model_id is required for ai provenance",
    )


def test_task_and_agent_observations_always_require_origin_task():
    assert validate_relation_provenance("manual", actor_type="agent") == (
        "origin_task_id is required for agent observation",
    )
    assert validate_relation_provenance(
        "manual", actor_type="task_executor", origin_task_id="task"
    ) == ()


def test_split_and_merged_from_share_one_union_cycle_graph():
    existing = [
        relation_key("split_from", "Paper", "b", "Paper", "a"),
        relation_key("merged_from", "Paper", "c", "Paper", "b"),
    ]
    assert would_create_relation_cycle(
        existing, relation_key("split_from", "Paper", "a", "Paper", "c")
    )


def test_extends_cycles_are_checked_independently_per_entity_type():
    existing = [relation_key("extends", "Idea", "b", "Idea", "a")]
    assert would_create_relation_cycle(
        existing, relation_key("extends", "Idea", "a", "Idea", "b")
    )
    assert not would_create_relation_cycle(
        existing, relation_key("extends", "Note", "a", "Note", "b")
    )
    assert not would_create_relation_cycle(
        existing, relation_key("related_to", "Idea", "a", "Idea", "b")
    )
