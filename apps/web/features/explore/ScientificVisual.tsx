/** Catalog placeholder; never substitute a taxonomic cue for specimen media. */
export function SpecimenVisual({ compact = false }: { compact?: boolean }) {
  return <div className={compact ? "specimen-placeholder compact" : "specimen-placeholder"}>
    <svg viewBox="0 0 80 60" aria-hidden="true"><rect x="12" y="9" width="56" height="42" rx="2" fill="none" stroke="currentColor" /><path d="M21 20h38M21 28h26M21 39h16" stroke="currentColor" /><circle cx="58" cy="41" r="3" fill="none" stroke="currentColor" /></svg>
    {!compact && <p><strong>Specimen image unavailable</strong><span>Cataloged material / no verified image displayed</span></p>}
  </div>;
}
