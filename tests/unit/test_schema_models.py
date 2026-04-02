"""Focused v4 schema model tests for Phase 1."""

from __future__ import annotations

from shruggie_indexer.models.schema import PredicateResult, RelationshipAnnotation


def test_predicate_result_to_dict_optional_fields() -> None:
    pred = PredicateResult(name="requires_sibling", satisfied=False)
    assert pred.to_dict() == {"name": "requires_sibling", "satisfied": False}


def test_relationship_annotation_to_dict() -> None:
    rel = RelationshipAnnotation(
        target_id="y123",
        type="description",
        rule="yt-dlp-description",
        rule_source="builtin",
        confidence=2,
        predicates=[PredicateResult(name="match", satisfied=True)],
    )
    payload = rel.to_dict()
    assert payload["target_id"] == "y123"
    assert payload["confidence"] == 2
    assert payload["predicates"][0]["name"] == "match"
