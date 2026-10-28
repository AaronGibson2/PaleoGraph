"use client";

import { useEffect, useRef } from "react";
import type { EntityRef } from "../../lib/api/discovery";
import { Localities } from "../explore/Localities";

/** Reuses the source locality presentation, including its scientific caveats. */
export function AtlasLocalityDossier({ id, identity, context, onPivot, onClose, onClear, onMaterial, onLineage, onGraph }: { id: string; identity?: EntityRef; context: string; onPivot: (entity: EntityRef) => void; onClose: () => void; onClear: () => void; onMaterial: () => void; onLineage: () => void; onGraph: () => void }) {
  const drawer = useRef<HTMLElement>(null);
  useEffect(() => { drawer.current?.querySelector<HTMLElement>("h2")?.focus({preventScroll:true}); }, [id]);
  return <aside ref={drawer} className="atlas-locality-dossier" aria-label="Locality dossier" onKeyDown={event => { if(event.key === "Escape") onClose(); }}>
    <div className="atlas-drawer-edition"><span>PALEOGRAPH / LOCALITY DOSSIER</span><button className="atlas-dossier-graph" aria-label="Explore relationships" onClick={onGraph}>Connections ↗</button><button aria-label="Close locality dossier" onClick={onClose}>×</button></div>
    <Localities embedded id={id} identity={identity} context={context} onPivot={onPivot} onClear={onClear} onAtlas={onClose} onMaterial={onMaterial} onLineage={onLineage} />
  </aside>;
}
