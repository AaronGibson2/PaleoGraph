/** Original schematic clade glyphs. Classification cues, never specimen images. */
export function TaxonIcon({ classification = [] }: { classification?: string[] }) {
  const labels = new Set(classification);
  const clade = labels.has("Aves") ? "bird" : labels.has("Mammalia") ? "mammal" : labels.has("Amphibia") ? "amphibian" : labels.has("Reptilia") ? "reptile" : ["Actinopterygii", "Chondrichthyes", "Osteichthyes"].some(label => labels.has(label)) ? "fish" : "unassigned";
  const paths: Record<string, string> = {
    mammal: "M8 31 Q18 12 41 18 L49 10 53 19 63 24 61 31 50 30 46 44 41 44 42 31 26 32 22 44 17 44 18 30 11 34 3 23 7 21Z",
    bird: "M7 43 Q23 38 29 27 Q23 17 7 11 Q27 8 42 24 L48 14 Q52 10 56 15 L63 18 57 21 Q54 31 43 35 L41 47 37 47 37 36 Q24 43 7 43Z",
    fish: "M15 28 Q33 11 50 21 L58 14 57 28 61 40 50 35 Q32 43 15 28Z M28 19 34 9 39 19 M29 37 35 46 40 36",
    reptile: "M3 38 Q15 29 27 29 Q31 19 45 23 L52 17 58 20 63 26 54 30 42 31 47 42 43 44 35 34 25 35 21 44 17 41 20 32 Q9 38 3 38Z",
    amphibian: "M15 37 8 27 12 23 23 31 28 24 25 17 29 14 35 22 40 15 45 18 42 28 51 30 57 24 61 29 52 40 43 35 36 40 27 36 20 43Z",
    unassigned: "M32 10 54 28 32 46 10 28Z M32 20 42 28 32 36 22 28Z",
  };
  return <svg className={`taxon-icon taxon-icon-${clade}`} viewBox="0 0 68 56" aria-hidden="true" focusable="false"><path d={paths[clade]} fill="currentColor" fillRule="evenodd" /></svg>;
}

export function SpecimenVisual({ compact = false }: { compact?: boolean }) {
  return <div className={compact ? "specimen-placeholder compact" : "specimen-placeholder"}>
    <svg viewBox="0 0 80 60" aria-hidden="true"><rect x="12" y="9" width="56" height="42" rx="2" fill="none" stroke="currentColor" /><path d="M21 20h38M21 28h26M21 39h16" stroke="currentColor" /><circle cx="58" cy="41" r="3" fill="none" stroke="currentColor" /></svg>
    {!compact && <p><strong>Specimen image unavailable</strong><span>Cataloged material / no verified image displayed</span></p>}
  </div>;
}
