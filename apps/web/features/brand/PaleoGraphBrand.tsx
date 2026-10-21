/** A branching P over two strata: classification, place and a retained record. */
export function BrandMark() {
  return <svg className="brand-mark" viewBox="0 0 40 40" fill="none" aria-hidden="true" focusable="false"><path d="M10 33V7h12a9 9 0 0 1 0 18H10m0 0 12-10M19 31h13M19 36h8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><circle cx="23" cy="14" r="2.5" fill="currentColor" /></svg>;
}

export function PaleoGraphBrand({ compact = false }: { compact?: boolean }) {
  return <span className={`paleograph-brand${compact ? " paleograph-brand-compact" : ""}`}><BrandMark />{!compact && <span className="brand-word">Paleo<span>Graph</span></span>}</span>;
}
