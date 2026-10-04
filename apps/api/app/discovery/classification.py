"""Rebuildable source-rank membership; never evolutionary ancestry."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

RANK = (
    "array_position(ARRAY['kingdom','phylum','class','order','family','genus','species'], "
    "{alias}.rank)"
)
PARENTS = f"""parents AS (
    SELECT DISTINCT ON (p.ancestor_id) p.ancestor_id id, a.ancestor_id parent_id
    FROM taxon_path p JOIN taxon child ON child.id=p.ancestor_id
    LEFT JOIN taxon_path a ON a.taxon_id=p.taxon_id AND a.ancestor_id<>p.ancestor_id
        AND a.ancestor_id<>a.taxon_id AND EXISTS (SELECT 1 FROM taxon parent
            WHERE parent.id=a.ancestor_id AND (p.ancestor_id=p.taxon_id OR
                {RANK.format(alias="parent")} < {RANK.format(alias="child")}))
    LEFT JOIN taxon parent ON parent.id=a.ancestor_id
    ORDER BY p.ancestor_id, {RANK.format(alias="parent")} DESC NULLS LAST,a.ancestor_id
)"""


LINK_SQL = f"WITH {PARENTS} SELECT id,parent_id FROM parents"


def classification_contexts(
    session: Session, identifiers: list[UUID]
) -> dict[str, dict[str, list[str]]]:
    """One bounded batch: source membership IDs nearest-first, labels root-first."""
    if not identifiers:
        return {}
    rows = session.execute(
        text("""WITH RECURSIVE trail AS (
        SELECT taxon_id origin,taxon_id,parent_taxon_id,0 depth FROM classification_link
        WHERE taxon_id=ANY(:ids) UNION ALL
        SELECT t.origin,p.taxon_id,p.parent_taxon_id,t.depth+1 FROM classification_link p
        JOIN trail t ON p.taxon_id=t.parent_taxon_id WHERE t.depth<10)
        SELECT origin,t.id,t.scientific_name FROM trail JOIN taxon t ON t.id=trail.taxon_id
        ORDER BY depth"""),
        {"ids": list(dict.fromkeys(identifiers))},
    ).all()
    result: dict[str, dict[str, list[str]]] = {}
    for origin, identifier, name in rows:
        context = result.setdefault(
            str(origin), {"classification": [], "classification_path_ids": []}
        )
        context["classification"].insert(0, name)
        context["classification_path_ids"].append(str(identifier))
    return result


def classification_labels(session: Session, identifiers: list[UUID]) -> dict[str, list[str]]:
    return {
        key: value["classification"]
        for key, value in classification_contexts(session, identifiers).items()
    }


def common_classification(contexts: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    """Only shared membership is safe when a specimen has differing identifications."""
    if not contexts:
        return {}
    shared = set(contexts[0]["classification_path_ids"])
    for context in contexts[1:]:
        shared.intersection_update(context["classification_path_ids"])
    first = contexts[0]
    pairs = zip(first["classification_path_ids"], reversed(first["classification"]), strict=True)
    kept = [(identifier, label) for identifier, label in pairs if identifier in shared]
    return {
        "classification_path_ids": [identifier for identifier, _ in kept],
        "classification": [label for _, label in reversed(kept)],
    }
