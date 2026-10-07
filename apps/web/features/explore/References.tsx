"use client";

import { useState } from "react";
import { discovery, type EntityKind, type EntityRef, type ReferenceItem } from "../../lib/api/discovery";
import { browseKey } from "./browseCache";
import { useResource } from "./useResource";

export function ReferenceCitation({ item }: { item: ReferenceItem }) {
  const doi = item.doi?.replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "");
  return <><p className="evidence-source">PBDB · {item.role === "reference" ? "bibliographic record" : `${item.role} reference`} · {item.published_year ?? "Year not supplied"}</p><p>{item.authors}</p><strong>{item.title ?? `PBDB reference ${item.external_id}`}</strong>{item.publication && <p>{item.publication}</p>}{doi && <p><a href={`https://doi.org/${encodeURIComponent(doi).replaceAll("%2F", "/")}`} target="_blank" rel="noopener noreferrer">DOI: {doi} ↗</a></p>}<a href={`https://paleobiodb.org/classic/displayReference?reference_no=${encodeURIComponent(item.external_id)}`} target="_blank" rel="noopener noreferrer">PBDB reference ↗</a></>;
}

export function References({ kind, id, context = "", onPivot }: { kind: EntityKind; id: string; context?: string; onPivot: (entity: EntityRef) => void }) {
  const [open,setOpen] = useState(false);
  const [navigation,setNavigation] = useState<{base:string;cursors:string[]}>({base:"",cursors:[]});
  const [retry,setRetry] = useState(0);
  const base=`${kind}/${id}?${context}`;
  const cursors=navigation.base===base ? navigation.cursors : [];
  const query=`${context}&limit=10${cursors.length ? `&cursor=${encodeURIComponent(cursors.at(-1)!)}` : ""}`;
  const result=useResource(open ? browseKey(`/entities/${kind}/${id}/references`,query) : null,signal=>discovery.references(kind,id,query,signal),0,retry);
  return <section className="reference-evidence"><button className="scientific-link" aria-expanded={open} onClick={()=>setOpen(!open)}>Publication evidence {open ? "−" : "+"}</button>{open && <><p className="context-note">Explicit identification, collection, material and taxonomic-opinion reference roles. A cited opinion is source evidence, not a new taxonomic relationship.</p><p role="status">{result.data ? `${result.data.total} reference roles` : "Reading publication evidence…"}{result.loading && result.data && " · Updating"}</p><ol>{result.data?.items.map(item=><li key={`${item.id}:${item.role}:${item.evidence_source_record_id}`}><ReferenceCitation item={item} /><button onClick={()=>onPivot({kind:"reference",id:item.id,label:item.title ?? `PBDB reference ${item.external_id}`,subtitle:item.published_year,source:"pbdb"})}>Inspect reference ↗</button></li>)}</ol>{result.data?.total===0 && <p>No explicit reference roles match this context.</p>}{result.error && <p role="alert">{result.error}<button onClick={()=>setRetry(retry+1)}>Retry references</button></p>}<div className="association-pagination"><button disabled={!cursors.length || result.loading} onClick={()=>setNavigation({base,cursors:cursors.slice(0,-1)})}>Previous references</button><button disabled={!result.data?.next_cursor || result.loading} onClick={()=>setNavigation({base,cursors:[...cursors,result.data!.next_cursor!]})}>Next references</button></div></>}</section>;
}
