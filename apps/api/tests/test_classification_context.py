"""Compact membership paths, including safe multi-identification material context."""

from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.discovery.classification import classification_contexts, common_classification
from app.discovery.queries import catalog, entity_ref, search
from app.discovery.schemas import ContextQuery

pytest_plugins = ["test_associations"]


def test_conflicting_identifications_keep_only_common_membership() -> None:
    assert common_classification(
        [
            {
                "classification_path_ids": ["horse", "mammal", "animal"],
                "classification": ["Animalia", "Mammalia", "Equus"],
            },
            {
                "classification_path_ids": ["rodent", "mammal", "animal"],
                "classification": ["Animalia", "Mammalia", "Rodentia"],
            },
        ]
    ) == {
        "classification_path_ids": ["mammal", "animal"],
        "classification": ["Animalia", "Mammalia"],
    }
    assert common_classification([{"classification": [], "classification_path_ids": []}]) == {
        "classification": [],
        "classification_path_ids": [],
    }
    assert common_classification([]) == {}


@pytest.mark.integration
def test_paths_are_batched_nearest_first_and_shared_by_result_contracts(material: Session) -> None:
    page = catalog(material, ContextQuery(limit=100))
    ids = [item.taxon_id for item in page.items]
    statements: list[str] = []

    def capture(_connection, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(material.bind, "before_cursor_execute", capture)
    try:
        contexts = classification_contexts(material, ids + ids)
    finally:
        event.remove(material.bind, "before_cursor_execute", capture)
    assert len(statements) == 1
    assert classification_contexts(material, []) == {}
    assert classification_contexts(material, [uuid4()]) == {}
    for item in page.items:
        assert item.classification_path_ids[0] == item.taxon_id
        context = contexts[str(item.taxon_id)]
        assert list(map(str, item.classification_path_ids)) == context["classification_path_ids"]
        entity = entity_ref(material, "taxon", item.taxon_id)
        assert entity.classification_path_ids == item.classification_path_ids
        assert entity.classification[-1] == item.scientific_name
        specimen = entity_ref(material, "specimen", item.specimen_id)
        assert specimen.classification_path_ids
    result = search(material, ContextQuery(q="Smilodon", limit=100))
    specimens = [item for item in result.items if item.kind == "specimen"]
    assert specimens and all(item.classification_path_ids for item in specimens)
