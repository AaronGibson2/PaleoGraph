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


def classification_labels(session: Session, identifiers: list[UUID]) -> dict[str, list[str]]:
    if not identifiers:
        return {}
    rows = session.execute(
        text("""WITH RECURSIVE trail AS (
        SELECT taxon_id origin,taxon_id,parent_taxon_id,0 depth FROM classification_link
        WHERE taxon_id=ANY(:ids) UNION ALL
        SELECT t.origin,p.taxon_id,p.parent_taxon_id,t.depth+1 FROM classification_link p
        JOIN trail t ON p.taxon_id=t.parent_taxon_id WHERE t.depth<10)
        SELECT origin,t.scientific_name FROM trail JOIN taxon t ON t.id=trail.taxon_id
        ORDER BY depth DESC"""),
        {"ids": identifiers},
    ).all()
    result: dict[str, list[str]] = {}
    for origin, name in rows:
        result.setdefault(str(origin), []).append(name)
    return result
