"use client";

import { useState } from "react";
import { discovery, type EntityKind, type EntityRef, type GraphPage } from "../../lib/api/discovery";
import { useResource } from "./useResource";

export function Relationships({ kind, id, context, onPivot, retry }: { kind: EntityKind; id: string; context: string; onPivot: (entity: EntityRef) => void; retry: number }) {
  const base = `${kind}:${id}:${context}:${retry}`;
  const [navigation, setNavigation] = useState<{ base: string; cursor: string | null; previous?: GraphPage }>({ base: "", cursor: null });
  const cursor = navigation.base === base ? navigation.cursor : null;
  const query = `${context}&limit=12${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
  const result = useResource<GraphPage>(`${base}:${cursor}`, signal => discovery.graph(kind, id, query, signal));
  const previous = navigation.base === base ? navigation.previous : undefined;
  const page = result.data;
  const data = page && previous ? { ...page,
    nodes: [...new Map([...previous.nodes, ...page.nodes].map(node => [`${node.kind}:${node.id}`, node])).values()],
    edges: [...new Map([...previous.edges, ...page.edges].map(edge => [edge.target, edge])).values()],
  } : page;
  const neighbors = data?.nodes.slice(1) ?? [];
  const height = Math.max(600, Math.ceil(neighbors.length / 2) * 90 + 50);
  return <section className="relationship-surface" aria-labelledby="graph-heading" aria-busy={result.loading}>
    <div className="graph-heading"><p className="eyebrow">A record, in relation</p><h2 id="graph-heading">Follow the material.</h2><p>Published classification, holding collections and source context.<br />Associations share catalog material; they are not inferred biological relationships.</p></div>
    {!data && <p role="status">{result.error ?? "Reading relationships…"}</p>}
    {data && <>
      <div className="graph-pagination"><p role="status">{neighbors.length} in view / {data.total_neighbors.toLocaleString("en-US")} supported neighbors{result.loading ? " · Updating…" : ""}{neighbors.length >= 24 ? " · 24-node view limit" : ""}</p>{cursor && <button onClick={() => setNavigation({ base, cursor: null })}>First neighborhood</button>}<button disabled={!data.next_cursor || result.loading} onClick={() => setNavigation({ base, cursor: data.next_cursor, previous: neighbors.length < 24 ? data : undefined })}>{neighbors.length < 24 ? "Expand neighborhood" : "Continue to next neighborhood"} →</button></div>
      <div className="graph-instrument" style={{ height: neighbors.length > 12 ? `${height * .74}px` : undefined }}>
        <svg className="graph-lines" viewBox={`0 0 1000 ${height}`} preserveAspectRatio="none" aria-hidden="true">{neighbors.map((node, index) => { const left = index % 2 === 0; const row = Math.floor(index / 2); const y = 55 + row * 90; return <path key={`${node.kind}:${node.id}`} d={`M 500 ${height / 2} C ${left ? 320 : 680} ${height / 2}, ${left ? 360 : 640} ${y}, ${left ? 230 : 770} ${y}`} />; })}</svg>
        <div className="graph-root"><span>{data.root.kind}</span><h3>{data.root.label}</h3><small>{data.root.subtitle}</small><span className="graph-root-ring" aria-hidden="true" /></div>
        {neighbors.map((node, index) => <button key={`${node.kind}:${node.id}`} className={`graph-node graph-node-${node.kind}`} style={{ left: index % 2 === 0 ? "3%" : "73%", top: `${(55 + Math.floor(index / 2) * 90) / height * 100}%` }} onClick={() => onPivot(node)}><small>{node.kind} / {node.subtitle}</small><strong>{node.label}</strong><span>Recenter ↗</span></button>)}
      </div>
      <details className="graph-accessible"><summary>Accessible relationship list</summary><ul>{data.edges.map(edge => { const node = data.nodes.find(item => `${item.kind}:${item.id}` === edge.target)!; return <li key={edge.target}>{data.root.label} — {edge.label} — <button onClick={() => onPivot(node)}>{node.label} ({node.kind})</button></li>; })}</ul></details>
    </>}
    {result.error && <p role="alert">{result.error}. Last loaded neighborhood remains visible.</p>}
  </section>;
}
