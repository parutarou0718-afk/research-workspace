# Gate 2 Freeze Ledger

## Baseline

- Status: `FROZEN`
- Freeze commit: `2a5f033aa721e4ad8ef75b0ecc3eac127cf3d477`
- Alembic revision: `0003_gate2_monitoring`
- Domain events: DomainEvent 2.0 for all new writes; immutable DomainEvent 1.0 remains readable
- Candidate engine: Candidate detector 1.0
- Public-release evidence: `REL-GATE-001` remains `BLOCKED_BY_ENVIRONMENT`

This ledger fixes the accepted Gate 2 semantic and byte-level baseline used by
Gate 3. Gate 3 is implemented by forward addition and must not reinterpret or
rewrite these facts.

## Gate 2 Exclusive File Bytes

| Path | SHA-256 |
|---|---|
| `contracts/event_contract.schema.json` | `03bb82a8c2444c0a37a03c7e9c3818478e1dc36926c5be67195ee149370818fe` |
| `contracts/background_operation.schema.json` | `dfdd616ce8946ca5f53617f230e00428a7a68f973a27693128031852e0309208` |
| `migrations/versions/0003_gate2_monitoring.py` | `8a144eadff700c772d703d7f2ab28b9ba2124e663c481325c8dbf7ca855dfe47` |

These Gate 2-exclusive files remain byte-for-byte identical.

## Gate 2 Semantic Node Digests

`contracts/domain_model.json` is a shared, forward-extensible registry. Its
existing nodes are frozen by SHA-256 over UTF-8 JSON serialized with recursively
sorted object keys, compact separators, and preserved array order:

| Node | Semantic SHA-256 |
|---|---|
| `entities` | `20ae31f8998a1417fc77af92d7d2b59a7d698ed28e95daa5e6d42079753ec20b` |
| `gate1_entities` | `8d0971c2d12576ea3c3d23156b85c5ea8f0a200b4688381025f24fc45400fb1e` |
| `gate2_entities` | `b0160e245f74cd7f5d375adc273dc0fee35f766d1c0f84ab57a16ca3356901d5` |
| `gate2_contracts` | `35c2abf73648852b994cb3fb21285cb444aa67b670712051121670c3fb4b858f` |
| `relation_types` | `d26e2460078c81cd5b3bc3f414e022da165c690851ac83c122bff8c685e53c11` |
| `confirmation_states` | `b3aaac73fbce6871fad6ffe68f53da4e6090e4f88ca61e7d0e696362518c4338` |
| `idea_statuses` | `11245c820a8468fd734075e2263d221b8c8e3de5acc56d380fd7fae3edf1a8d9` |
| `submission_statuses` | `d4d9e45724af5e76d9c7ad220092bb00900ab63c6a749d42dad661c311757b02` |

Gate 3 may change the document version from `0.2-gate2` to `0.2-gate3` and append
new `gate3_*` nodes. It may not delete, rename, or change any digest-protected
node. Gate 3 relation endpoints, transitions, and entity replacements belong in
new Gate 3 nodes rather than rewriting the legacy/Gate 2 nodes.

## Provider Interface Prefix

`contracts/provider_interfaces.md` is append-only after the accepted Gate 2
content:

- Prefix length: `6589` bytes
- Prefix SHA-256: `7a8c1181912c6fd1f950c135c30161ad1f7f9081553021283de271f5301ad1c4`

Every byte in that prefix remains unchanged and in the same order. Gate 3
interfaces may be appended after it; existing sections may not be rewritten or
reordered.

Each Gate 3 Checkpoint reports `Gate 2 Freeze Verification` with:

```text
Migration: PASS
Contracts: PASS
Semantic Nodes: PASS
Provider Prefix: PASS
Scheduler: PASS
Monitoring: PASS
```

## Candidate Identity and Rules

The immutable PaperVersionCandidate identity is exactly:

1. `earlier_snapshot_id`
2. `later_snapshot_id`
3. `detector_id`
4. `detector_version`
5. `rule_config_fingerprint`

The detector registry remains closed at version 1.0:

- `R1_SOURCE_CONTINUITY`
- `R2_REPLACE_CONTINUITY`
- `R3_PAPER_TITLE_TIME`
- `R4_NAME_TITLE_TEXT`
- `R5_ZERO_TEXT_LINEAGE`

Candidate decision state is separate from candidate identity and evidence. Gate
3 may confirm, reject, or reconsider through protected commands, but it cannot
rewrite detector evidence or candidate identity.

## Scheduler Constraints

- A new snapshot schedules at most `12` distinct comparisons.
- The neighborhoods are at most two continuity, five Paper, and five
  filename-lineage neighbors before deduplication.
- The 10,000-snapshot fixture schedules no more than 120,000 comparisons.
- No repository or service may expose or perform all-pairs enumeration.

## Monitoring Semantics

- The observation boundary remains
  `RawFileEvent -> PendingPathCheck -> SourceObservation`.
- Filesystem callbacks only enqueue immutable event facts.
- Baselines are metadata-only and do not hash, snapshot, parse, or detect.
- Same-hash relocation preserves provenance without creating a snapshot or
  candidate.
- Healthy operation performs no periodic full traversal.
- Reconciliation remains root-scoped, paged, checkpointed, cancellable, and
  triggered only by approved evidence.
- Disconnect, permission loss, degradation, and queue overflow never imply that
  every child source is missing.

## Frozen Surface

The following Gate 2 surfaces are frozen:

- contracts and migration 0003;
- candidate identity and detector evidence;
- detector version 1.0 and R1-R5 semantics;
- the at-most-12 comparison scheduler;
- monitoring roots, raw events, pending checks, observations, health,
  reconciliation, shutdown, and restart semantics;
- Gate 2 read-only candidate UI meaning.

Gate 3 consumes these facts through existing read interfaces. It does not
backfill, reinterpret, or silently revise them.

## Hotfix Policy

A Gate 2 modification is allowed only for a separately reviewed:

- Critical correctness defect
- Security defect
- Data-corruption defect

All other needs are implemented as Gate 3 forward addition. An approved
exception must identify the defect, affected frozen bytes or semantics,
compatibility impact, regression evidence, and replacement freeze hash. Product
convenience, UI implementation ease, refactoring preference, or a new Gate 3
requirement is not an exception.
