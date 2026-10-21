"use client";

import "./dossier.css";

export type DossierSectionLink = { id: string; label: string };

/** In-panel navigation deliberately leaves the shareable browse URL untouched. */
export function SectionIndex({ sections }: { sections: DossierSectionLink[] }) {
  if (sections.length < 2) return null;
  return <nav className="section-index" aria-label="Dossier sections">{sections.map(section => <button key={section.id} onClick={() => {
    const target = document.getElementById(section.id);
    if (!target) return;
    if (target instanceof HTMLDetailsElement) target.open = true;
    target.scrollIntoView({ block: "start" });
    const heading = target.matches("h2,h3,h4") ? target : target.querySelector<HTMLElement>("h2,h3,h4,summary");
    heading?.focus({ preventScroll: true });
  }}>{section.label}</button>)}</nav>;
}
