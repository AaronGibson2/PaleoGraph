"use client";

import { useCallback, useEffect, useReducer, useRef, useState, type KeyboardEvent } from "react";
import { taxonomy, type TaxonomyNode, type TaxonomyPage, type TaxonomyDetail, type PbdbHierarchy } from "../../lib/api/taxonomy";
import type { EntityRef } from "../../lib/api/discovery";
import type { AgeRange, GeologicalInterval } from "../../lib/api/types";
import { TaxonVisual } from "../taxon-visuals/TaxonVisual";
import { resolveTaxonVisual } from "../taxon-visuals/resolve";
import { ageLabel } from "./state";
import { browseCache, browseKey } from "./browseCache";
import { useResource } from "./useResource";
import { ExplorationToolbar } from "./ExplorationToolbar";
import "./taxonomy-polish.css";
import { adjacentRow, flattenTree, taxonomyContext, treeWindow, treeIndent, type Branch } from "./taxonomyTree";

const number = (value: number) => value.toLocaleString("en-US");
type Store = { key: string; branches: Record<string, Branch>; expanded: Set<string>; active: string; focusSerial: number };
type Action = { key: string } & (
  { type: "reset" } | { type: "expand"; id: string; open: boolean } |
  { type: "loading"; id: string } | { type: "page"; id: string; page: TaxonomyPage; append: boolean } |
  { type: "error"; id: string; error: string } | { type: "restore"; path: string[]; focus: string } |
  { type: "pages"; items: { parent_id: string; page: TaxonomyPage }[] } |
  { type: "active"; id: string; move: boolean }
);
const initial: Store = { key: "", branches: {}, expanded: new Set(), active: "", focusSerial: 0 };
function reducer(state: Store, action: Action): Store {
  if (action.type === "reset") return { ...initial, key: action.key };
  if (state.key !== action.key) return state;
  if (action.type === "active") return { ...state, active: action.id, focusSerial: state.focusSerial + Number(action.move) };
  if (action.type === "restore") return { ...state, expanded: new Set([...state.expanded, ...action.path]), active: action.focus, focusSerial: state.focusSerial + 1 };
  if (action.type === "expand") { const expanded = new Set(state.expanded); if (action.open) expanded.add(action.id); else expanded.delete(action.id); return { ...state, expanded }; }
  if (action.type === "loading") return { ...state, branches: { ...state.branches, [action.id]: { ...state.branches[action.id], loading: true, error: undefined } } };
  if (action.type === "error") return { ...state, branches: { ...state.branches, [action.id]: { ...state.branches[action.id], loading: false, error: action.error } } };
  if (action.type === "pages") {
    const branches = { ...state.branches };
    for (const item of action.items) {
      const previous = branches[item.parent_id]?.page;
      const incoming = item.page;
      const preservePages = previous && previous.version === incoming.version && previous.total === incoming.total && previous.items.length > incoming.items.length;
      const firstIds = new Set(incoming.items.map(node => node.id));
      const page = preservePages ? { ...incoming, items: [...incoming.items, ...previous.items.slice(incoming.items.length).filter(node => !firstIds.has(node.id))], next_offset: previous.next_offset } : incoming;
      branches[item.parent_id] = { page, loading: false };
    }
    return { ...state, branches };
  }
  const previous = state.branches[action.id]?.page;
  const page = action.append && previous ? { ...action.page, items: [...previous.items, ...action.page.items] } : action.page;
  return { ...state, branches: { ...state.branches, [action.id]: { page, loading: false } } };
}

type Props = { focus?: string | null; activeTaxon?: string | null; context: string; age: AgeRange; intervals: GeologicalInterval[]; onFocus: (id: string | null) => void; onResolved: (id: string) => void; onSelect: (entity: EntityRef) => void; onAtlas: (taxon: string | null) => void; onLocalities: (taxon: string | null) => void; onMaterial: (taxon: string | null) => void };

function HierarchyEvidence({ value }: { value?: PbdbHierarchy }) {
  if (!value?.orig_no) return null;
  return <div className="taxonomy-source-hierarchy">
    {value.relationship === "accepted identification context" && <p>Unresolved entered identity. Shown in the accepted identification&apos;s classification context; this final link does not assert a taxonomic child relationship.</p>}
    {value.partial_reason && <p>PBDB classification partial: {value.partial_reason}.</p>}
    <small>PBDB name: {value.taxon_name} ({value.taxon_rank ?? "rank not supplied"}) · {value.orig_no} · variant {value.taxon_no}</small>
    {value.accepted_no && <small>Accepted: {value.accepted_name ?? value.accepted_no} · {value.accepted_no}{value.difference ? ` · ${value.difference}` : ""}</small>}
    <small>PBDB parent: {value.immpar_name ?? value.parent_name ?? value.immpar_no ?? value.parent_no ?? "not supplied"} · {value.immpar_no ?? value.parent_no ?? "not supplied"}</small>
    {value.routing && <small>{value.routing}</small>}
    {value.identity_resolution && <small>PBDB omitted the entered identifier because it equals the accepted identifier; the source name and rank agree.</small>}
    <details><summary>Classification evidence and archived revision</summary>
      {value.reference_no && <small>Name authority reference: {value.reference_no}</small>}
      {value.classification_opinions?.length ? value.classification_opinions.map(opinion => <small key={opinion.opinion_no}>Classification opinion {opinion.opinion_no}: {opinion.status} · parent {opinion.parent_no ?? "not supplied"} · {opinion.reference_no ?? "reference not supplied"}{opinion.basis ? ` · ${opinion.basis}` : ""}{opinion.primary_reference ? ` · ${opinion.primary_reference}` : ""}</small>) : <small>No selected classification opinion supplied. Parent evidence is the archived PBDB taxon response.</small>}
      {value.snapshot_hash && <small>Taxonomy snapshot: <code>{value.snapshot_hash}</code></small>}
      {value.proof && <small>Source revision: <code>{value.proof.row_hash ?? value.proof.content_hash}</code>{value.proof.object ? <> · archive <code>{value.proof.object}</code></> : null}</small>}
    </details>
  </div>;
}

function ConceptList({ detail, query, onSelect }: { detail: TaxonomyDetail; query: string; onSelect: Props["onSelect"] }) {
  const [offset, setOffset] = useState(0);
  const [retry, setRetry] = useState(0);
  const params = new URLSearchParams(query); params.set("limit", "30"); params.set("offset", String(offset));
  const value = params.toString();
  const key = offset ? browseKey(`/taxonomy/nodes/${detail.node.id}/concepts`, value) : null;
  const page = useResource(key, signal => taxonomy.concepts(detail.node.id, value, signal), 0, retry);
  const concepts = offset ? page.dataKey === key ? page.data?.items ?? [] : [] : detail.concepts;
  return <section><h4>Underlying source concepts</h4><p>{number(detail.concept_total)} retained classification / identification memberships. Provenance includes both sources regardless of the evidence filter.</p>
    {key && page.loading && <p role="status">Loading source concepts...</p>}
    {page.error && <p role="alert">{page.error} <button onClick={() => setRetry(value => value + 1)}>Retry concepts</button></p>}
    <ul className="taxonomy-concepts">{concepts.map(concept => <li key={`${concept.source}:${concept.concept_key}`}><strong>{concept.source.toUpperCase()} · {concept.details.name}</strong><small>{concept.details.supplied_path.map(term => term.name).join(" › ")}{concept.details.qualifiers.length ? ` · ${concept.details.qualifiers.join(", ")}` : ""}{concept.details.upper_path_placement ? " · upper context placed using a unique supported classification" : ""}</small><small>Source concept: <code>{concept.concept_key}</code></small><HierarchyEvidence value={concept.details.hierarchy} />{concept.taxon_id && <button onClick={() => onSelect({ kind: "taxon", id: concept.taxon_id!, label: concept.details.name, subtitle: concept.details.rank, source: concept.source })}>Inspect source concept</button>}</li>)}</ul>
    {detail.concept_total > 30 && <div className="taxonomy-pagination"><span>{offset + 1}–{Math.min(offset + 30, detail.concept_total)} of {number(detail.concept_total)}</span><button disabled={!offset} onClick={() => setOffset(value => Math.max(0, value - 30))}>Previous concepts</button><button disabled={offset + 30 >= detail.concept_total || page.loading} onClick={() => setOffset(value => value + 30)}>Next concepts</button></div>}
  </section>;
}

export function Lineage({ focus, activeTaxon, context, onFocus, onResolved, onSelect, onAtlas, onLocalities, onMaterial }: Props) {
  const query = taxonomyContext(context);
  const [store, dispatch] = useReducer(reducer, initial);
  const [search, setSearch] = useState("");
  const [searchIndex, setSearchIndex] = useState(-1);
  const [chosenConcept, setChosenConcept] = useState<{ node: string; taxon: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const [pathFailure, setPathFailure] = useState<{ key: string; error: string } | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const scroller = useRef<HTMLDivElement>(null);
  const controllers = useRef<Set<AbortController>>(new Set());
  const pathAttempt = useRef({ key: "", retry: 0 });
  const rootKey = browseKey("/taxonomy/roots", query);
  const roots = useResource(rootKey, signal => taxonomy.roots(query, signal), 0, retry);
  const detailKey = focus ? browseKey(`/taxonomy/nodes/${focus}`, query) : null;
  const pathError = pathFailure?.key === detailKey ? pathFailure?.error : null;
  const detail = useResource(detailKey, signal => taxonomy.detail(focus!, query, signal), 0, retry);
  const searchQuery = new URLSearchParams(query); searchQuery.set("q", search); searchQuery.set("limit", "20");
  const searchKey = search.trim().length >= 2 ? browseKey("/taxonomy/search", searchQuery.toString()) : null;
  const matches = useResource(searchKey, signal => taxonomy.search(searchQuery.toString(), signal), 180, retry);
  const current = store.key === query ? store : initial;
  const data = detail.dataKey === detailKey ? detail.data : undefined;
  const rootNodes = roots.dataKey === rootKey ? roots.data?.items ?? [] : [];
  // A searched path remains reachable even if its root is beyond the first page.
  const pathRoot = data?.ancestors[0] ?? data?.node;
  const representedRoots = pathRoot && pathRoot.parent_id === null && !rootNodes.some(node => node.id === pathRoot.id) ? [...rootNodes, pathRoot] : rootNodes;
  const representedBranches = { ...current.branches };
  for (const node of [...(data?.ancestors ?? []), ...(data ? [data.node] : [])]) {
    if (!node.parent_id) continue;
    const branch = representedBranches[node.parent_id];
    if (branch?.page && !branch.page.items.some(child => child.id === node.id)) {
      representedBranches[node.parent_id] = { ...branch, page: { ...branch.page, items: [...branch.page.items, node] } };
    }
  }
  const rows = flattenTree(representedRoots, representedBranches, current.expanded);
  const window = treeWindow(rows.length, scrollTop);
  const firstVisible = Math.floor(scrollTop / 58);
  const deepestVisible = Math.max(1, ...rows.slice(firstVisible, firstVisible + 11).map(row => row.level));
  const load = useCallback(async (id: string, offset = 0) => {
    const params = new URLSearchParams(query); if (offset) params.set("offset", String(offset));
    const value = params.toString(); const key = browseKey(`/taxonomy/nodes/${id}/children`, value);
    const controller = new AbortController(); controllers.current.add(controller);
    dispatch({ type: "loading", key: query, id });
    try {
      const page = await browseCache.load(key, signal => taxonomy.children(id, value, signal), controller.signal);
      if (!controller.signal.aborted) dispatch({ type: "page", key: query, id, page, append: offset > 0 });
      return page;
    } catch (error) {
      if (!controller.signal.aborted) dispatch({ type: "error", key: query, id, error: error instanceof Error ? error.message : "Classification could not load." });
      return undefined;
    } finally { controllers.current.delete(controller); }
  }, [query, dispatch]);
  useEffect(() => {
    dispatch({ type: "reset", key: query });
    const active = controllers.current;
    return () => { for (const controller of active) controller.abort(); active.clear(); };
  }, [query]);
  useEffect(() => {
    if (!data || !detailKey || detail.loading || detail.error) return;
    if (focus !== data.node.id) { onResolved(data.node.id); return; }
    const controller = new AbortController();
    const force = pathAttempt.current.key === detailKey && pathAttempt.current.retry !== retry;
    pathAttempt.current = { key: detailKey, retry };
    void (async () => {
      let offset: number | null = 0;
      while (data.ancestors.length && offset !== null) {
        const params = new URLSearchParams(query); if (offset) params.set("offset", String(offset));
        const value = params.toString(); const key = browseKey(`/taxonomy/nodes/${data.node.id}/branch-children`, value);
        const page = await browseCache.load(key, signal => taxonomy.branch(data.node.id, value, signal), controller.signal, force);
        if (controller.signal.aborted) return;
        dispatch({ type: "pages", key: query, items: page.items });
        offset = page.next_offset;
      }
      if (!controller.signal.aborted) {
        if (data.ancestors.length) setPathFailure(null);
        dispatch({ type: "restore", key: query, path: data.ancestors.map(node => node.id), focus: data.node.id });
      }
    })().catch(error => { if (!controller.signal.aborted) setPathFailure({ key: detailKey, error: error instanceof Error ? error.message : "Classification path could not load." }); });
    return () => controller.abort();
  }, [data, detailKey, detail.loading, detail.error, query, focus, onResolved, retry]);
  const focusedIntent = useRef("");
  useEffect(() => {
    const intent = `${query}:${current.focusSerial}:${current.active}`;
    if (!current.focusSerial || focusedIntent.current === intent) return;
    const index = rows.findIndex(row => row.node.id === current.active);
    if (index < 0) return;
    const frame = requestAnimationFrame(() => {
      const element = scroller.current;
      if (element && rows.length > 120 && (index < window.start || index >= window.end)) {
        element.scrollTop = Math.max(0, index * 58 - 116);
        setScrollTop(element.scrollTop);
        return; // Focus after the newly visible rows have committed to the DOM.
      }
      const row = document.getElementById(`taxonomy-row-${current.active}`);
      if (row) { focusedIntent.current = intent; row.focus(); }
    });
    return () => cancelAnimationFrame(frame);
  }, [query, current.focusSerial, current.active, rows, window.start, window.end]);
  const expand = (node: TaxonomyNode, open = !current.expanded.has(node.id)) => {
    dispatch({ type: "expand", key: query, id: node.id, open });
    if (open && !current.branches[node.id]?.page) void load(node.id);
  };
  const prepare = (node: TaxonomyNode) => {
    if (!node.counts.child_count || current.branches[node.id]?.page) return;
    browseCache.prefetch(browseKey(`/taxonomy/nodes/${node.id}/children`, query), signal => taxonomy.children(node.id, query, signal));
  };
  const move = (id: string) => dispatch({ type: "active", key: query, id, move: true });
  const keyboard = (event: KeyboardEvent, node: TaxonomyNode) => {
    const next = adjacentRow(rows, node.id, event.key);
    if (next) { event.preventDefault(); move(next); }
    if (event.key === "ArrowRight" && node.counts.child_count) {
      event.preventDefault();
      if (!current.expanded.has(node.id)) expand(node, true);
      else { const child = current.branches[node.id]?.page?.items[0]; if (child) move(child.id); }
    }
    if (event.key === "ArrowLeft") { event.preventDefault(); if (current.expanded.has(node.id)) expand(node, false); else if (node.parent_id) move(node.parent_id); }
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onFocus(node.id); }
  };
  const selectedTaxon = activeTaxon ?? (chosenConcept?.node === data?.node.id ? chosenConcept?.taxon : null) ?? data?.concepts.find(concept => concept.source === "ufvp" && concept.taxon_id)?.taxon_id ?? data?.concepts.find(concept => concept.taxon_id)?.taxon_id ?? null;
  return <div className="scientific-surface lineage-surface taxonomy-surface" aria-label="Florida taxonomy explorer" aria-busy={roots.loading}>
    <div className="surface-introduction"><div><p className="eyebrow">Taxonomic hierarchy / observed classification</p><h2>Florida Taxonomy</h2><p>Browse source-supported classifications together. This is a reversible browse interpretation, not an evolutionary phylogeny.</p></div><span className="plate-number" aria-hidden="true">03 / LINEAGE</span></div>
    <ExplorationToolbar label="Taxonomy controls" className="taxonomy-tools"><div className="taxonomy-search"><label htmlFor="taxonomy-search">Find a taxonomic group</label><input id="taxonomy-search" type="search" placeholder="Search taxa, e.g. Canis" value={search} onChange={event => { setSearch(event.target.value); setSearchIndex(-1); }} onKeyDown={event => {
        const results = matches.dataKey === searchKey ? matches.data?.items ?? [] : [];
        if (event.key === "Escape") { setSearch(""); setSearchIndex(-1); }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setSearchIndex(index => Math.max(0, Math.min(results.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))); }
        if (event.key === "Enter" && results[searchIndex]) { event.preventDefault(); onFocus(results[searchIndex].id); setSearch(""); setSearchIndex(-1); }
      }} aria-activedescendant={searchIndex >= 0 && matches.dataKey === searchKey && matches.data?.items[searchIndex] ? `taxonomy-match-${matches.data.items[searchIndex].id}` : undefined} aria-controls="taxonomy-matches" role="combobox" aria-autocomplete="list" aria-haspopup="listbox" aria-expanded={!!searchKey} />
      {searchKey && <div id="taxonomy-matches" className="taxonomy-matches" role="listbox" aria-label="Taxonomy search results">{matches.loading && <p role="status">Searching classifications…</p>}{matches.error && <p role="alert">{matches.error}</p>}{matches.dataKey === searchKey && matches.data?.items.map((node, index) => <button id={`taxonomy-match-${node.id}`} key={node.id} role="option" aria-selected={searchIndex === index} onClick={() => { setSearch(""); onFocus(node.id); }}><strong>{node.name}</strong><small>{node.rank ?? "Rank not supplied"} · {node.sources.map(source => source.toUpperCase()).join(" · ")} · {node.path.slice(0, -1).map(term => term.name).join(" › ") || "Partial classification"}{node.placement !== "supported" ? ` · ${node.placement}${node.identity_hint ? ` · ${node.identity_hint}` : ""}` : ""}</small></button>)}{!matches.loading && matches.dataKey === searchKey && !matches.data?.items.length && <p>No matching classifications in this evidence context.</p>}</div>}
    </div></ExplorationToolbar>
    {(roots.error || detail.error || pathError) && <p className="snapshot-status" role="alert">{roots.error ?? detail.error ?? pathError} {roots.error && rootNodes.length > 0 ? "Showing the last loaded taxonomy snapshot." : ""} <button onClick={() => setRetry(value => value + 1)}>Retry taxonomy</button></p>}
    <div className="taxonomy-workspace">
      <section className="taxonomy-hierarchy" aria-label="Taxonomic hierarchy">
        <div className="taxonomy-column-labels"><span>GROUP / RANK</span><span>INCLUSIVE EVIDENCE</span></div>
        <div ref={scroller} className="taxonomy-scroll" onScroll={event => setScrollTop(event.currentTarget.scrollTop)}>
          <ul role="tree" aria-label="Florida taxonomic classifications" aria-busy={roots.loading} className="taxonomy-tree">
            {window.before > 0 && <li role="presentation" style={{ height: window.before }} />}
            {rows.slice(window.start, window.end).map(({ node, level, position, size }) => <li id={`taxonomy-row-${node.id}`} key={node.id} role="treeitem" aria-level={level} aria-posinset={position} aria-setsize={size} aria-expanded={node.counts.child_count ? current.expanded.has(node.id) : undefined} aria-selected={data?.node.id === node.id} tabIndex={current.active === node.id || (!current.active && rows[0]?.node.id === node.id) ? 0 : -1} className="taxonomy-row" data-rank={node.rank} title={`${node.name} · ${node.rank ?? "Rank not supplied"}`} style={{ paddingLeft: `calc(${(treeIndent(level, deepestVisible) - 8) / 19} * var(--taxonomy-indent, 19px) + 8px)` }} onMouseEnter={() => prepare(node)} onFocus={() => { prepare(node); dispatch({ type: "active", key: query, id: node.id, move: false }); }} onClick={() => onFocus(node.id)} onKeyDown={event => keyboard(event, node)}>
              <button tabIndex={-1} className="taxonomy-chevron" aria-label={`${current.expanded.has(node.id) ? "Collapse" : "Expand"} ${node.name}`} disabled={!node.counts.child_count} onClick={event => { event.stopPropagation(); if (current.branches[node.id]?.error) void load(node.id); else expand(node); }}>{node.counts.child_count ? current.expanded.has(node.id) ? "▾" : "▸" : "·"}</button>
              <TaxonVisual visual={resolveTaxonVisual({ id: node.id, classification_path_ids: node.classification_path_ids })} />
              <span className="taxonomy-name"><strong>{node.name}</strong><small>{node.rank ?? (node.placement === "container" ? "Browse grouping" : "Rank not supplied")} {node.placement !== "supported" && node.placement !== "container" ? `· ${node.placement}` : ""}{current.branches[node.id]?.loading ? " · Loading children…" : ""}</small></span>
              <span className="taxonomy-presence">{node.sources.map(source => <span key={source}>{source.toUpperCase()}</span>)}</span>
              <span className="taxonomy-count" aria-label={`${number(node.counts.evidence_count)} inclusive evidence records; ${number(node.counts.ufvp_material_count)} UFVP material records; ${number(node.counts.pbdb_occurrence_count)} PBDB occurrences; ${number(node.counts.direct_count)} direct evidence records`} title={`${number(node.counts.ufvp_material_count)} UFVP material records; ${number(node.counts.pbdb_occurrence_count)} PBDB occurrences; ${number(node.counts.direct_count)} direct evidence records`}><strong>{number(node.counts.evidence_count)}</strong><small>inclusive</small></span>
            </li>)}
            {window.after > 0 && <li role="presentation" style={{ height: window.after }} />}
          </ul>
          {roots.loading && !rootNodes.length && <p className="panel-message" role="status">Reading top-level classifications…</p>}
          {!roots.loading && !roots.error && !rows.length && <p className="panel-message">No indexed material or published occurrence evidence matches this context. Unknown ages are excluded by numeric age filters.</p>}
        </div>
        {Object.entries(current.branches).filter(([id, branch]) => current.expanded.has(id) && (branch.error || branch.page?.next_offset != null)).map(([id, branch]) => <div className="taxonomy-pagination" key={id}>{branch.error ? <span role="alert">{branch.error}</span> : <span>{rows.find(row => row.node.id === id)?.node.name}: {branch.page?.items.length} of {branch.page?.total} children</span>}<button disabled={branch.loading} onClick={() => void load(id, branch.error ? 0 : branch.page!.next_offset!)}>{branch.error ? "Retry children" : "Load more children"}</button></div>)}
        <p className="taxonomy-keyboard">↑ ↓ move · ← → collapse / expand · Enter selects. Counts include direct and descendant evidence; they are not individual specimens or organisms.</p>
      </section>
      <aside className="taxonomy-details" aria-label="Taxonomy node details" aria-busy={!!focus && detail.loading}>
        {!data ? <div className="taxonomy-empty"><p className="eyebrow">An evidence catalog</p><h3>Follow a classification.</h3><p>Expand a group to reveal its immediate children. Select any rank to inspect typed evidence counts, source concepts and observed temporal bounds.</p><p>Equal names with conflicting classifications or unresolved identity remain separate.</p></div> : <div className="lineage-focus taxonomy-focus">
          <p className="eyebrow">{data.node.rank ?? "Rank not supplied"} / {data.node.placement}</p><h3>{data.node.name}</h3>{data.node.identity_hint && <small className="taxonomy-identity">Source identity: <code>{data.node.identity_hint}</code></small>}
          <nav className="lineage-navigation" aria-label="Classification path"><button onClick={() => onFocus(null)}>All groups</button>{[...data.ancestors, data.node].map(node => <button key={node.id} aria-current={node.id === data.node.id ? "location" : undefined} onClick={() => onFocus(node.id)}>{node.name}</button>)}</nav>
          <dl className="taxonomy-evidence-counts"><div><dt>UFVP material-associated records</dt><dd>{number(data.node.counts.ufvp_material_count)}</dd></div><div><dt>PBDB published occurrences</dt><dd>{number(data.node.counts.pbdb_occurrence_count)}</dd></div><div><dt>Direct evidence at this node</dt><dd>{number(data.node.counts.direct_count)}</dd></div><div><dt>Inclusive evidence, including descendants</dt><dd>{number(data.node.counts.evidence_count)}</dd></div></dl>
          {!data.node.counts.evidence_count && <p role="status">This classification has no evidence in the selected source/context. Its stable identity remains available.</p>}
          <section className="taxonomy-time"><h4>Observed temporal evidence</h4><p>Aggregate outer envelope: <strong>{ageLabel(data.node.counts)}</strong></p><p>Source numeric bounds: <strong>{ageLabel({ older_ma: data.node.counts.source_older_ma, younger_ma: data.node.counts.source_younger_ma })}</strong> · {number(data.node.counts.source_numeric_count)} records</p><p>Interpreted reference envelopes: <strong>{ageLabel({ older_ma: data.node.counts.derived_older_ma, younger_ma: data.node.counts.derived_younger_ma })}</strong> · {number(data.node.counts.derived_count)} records</p><small>{number(data.node.counts.unknown_age_count)} records lack complete numeric bounds. Observed evidence is not origin, extinction or biological duration.</small></section>
          <ConceptList key={data.node.id} detail={data} query={query} onSelect={onSelect} />
          <section><h4>Evidence and locality preview</h4><p>Up to 12 represented evidence records. Open a record for identification history, qualifications and explicit references.</p><ul className="taxonomy-evidence">{data.evidence.map(item => <li key={item.occurrence_id}><button onClick={() => onSelect({ kind: item.kind, id: item.id, label: item.label, subtitle: item.scientific_name, source: item.source })}><strong>{item.label}</strong><small>{item.source.toUpperCase()} · {item.scientific_name} · {item.locality_name ?? "Locality not supplied"}</small></button></li>)}</ul></section>
          {selectedTaxon && <div className="taxonomy-source-actions"><label htmlFor="taxonomy-action-concept">Source concept for linked views</label><select id="taxonomy-action-concept" value={selectedTaxon} disabled={!!activeTaxon} onChange={event => setChosenConcept({ node: data.node.id, taxon: event.target.value })}>{activeTaxon && !data.concepts.some(concept => concept.taxon_id === activeTaxon) && <option value={activeTaxon}>Existing selected taxon context</option>}{data.concepts.filter(concept => concept.taxon_id).map(concept => <option key={`${concept.source}:${concept.concept_key}`} value={concept.taxon_id!}>{concept.source.toUpperCase()} · {concept.details.name} · {concept.details.rank ?? "Rank not supplied"}</option>)}</select><p>{activeTaxon ? "Linked views retain the existing selected taxon filter." : "Linked views use the source concept shown above."}</p><button onClick={() => onAtlas(selectedTaxon)}>Show on Atlas ↗</button><button onClick={() => onLocalities(selectedTaxon)}>Associated localities ↗</button><button onClick={() => onMaterial(selectedTaxon)}>Associated material ↗</button></div>}
        </div>}
      </aside>
    </div>
    <div className="scientific-caveat"><strong>Classification ≠ phylogeny. Occurrence ≠ specimen.</strong><p>Branches represent supported source classifications and explicit browse placement, never evolutionary ancestry. Missing ranks are not invented. Qualified identifications, conflicting paths and unresolved concepts remain inspectable. Source age bounds remain separate from interpreted reference envelopes. PBDB coordinates remain withheld.</p></div>
  </div>;
}
