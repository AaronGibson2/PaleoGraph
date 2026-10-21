import type { TaxonomyNode } from "../../lib/api/taxonomy";
import { ageLabel } from "./state";

/** Preview only retained node data. It never fetches or commits navigation. */
export function TaxonPreview({ node, top, left, onEnter, onLeave }: { node: TaxonomyNode; top: number; left: number; onEnter: () => void; onLeave: () => void }) {
  return <aside id="taxonomy-preview" className="taxon-preview" style={{ top, left }} aria-label={`Preview of ${node.name}`} onPointerEnter={onEnter} onPointerLeave={onLeave}>
    <p className="eyebrow">Classification preview / {node.rank ?? "rank not supplied"}</p>
    <h4>{node.name}</h4>
    <p className="preview-path">{node.path.map(term => term.name).join(" › ") || "Source path unresolved"}</p>
    <dl><div><dt>UFVP material records</dt><dd>{node.counts.ufvp_material_count.toLocaleString("en-US")}</dd></div><div><dt>PBDB occurrences</dt><dd>{node.counts.pbdb_occurrence_count.toLocaleString("en-US")}</dd></div><div><dt>Direct / inclusive evidence</dt><dd>{node.counts.direct_count.toLocaleString("en-US")} / {node.counts.evidence_count.toLocaleString("en-US")}</dd></div></dl>
    <p>Observed envelope <strong>{ageLabel(node.counts)}</strong></p>
    {!["supported", "container"].includes(node.placement) && <p className="preview-placement">Browse placement: {node.placement}. Source identity retained.</p>}
    <small>Preview only. Select to inspect source evidence. Escape dismisses.</small>
  </aside>;
}
