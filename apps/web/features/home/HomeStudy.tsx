"use client";

import Link from "next/link";
import { useRef, useState } from "react";

const studies = [
  { name: "Place", title: "Begin with a landscape.", copy: "Explore represented museum evidence on the map. Open a locality, meet its recorded fauna, and follow the material behind it.", href: "/explore", action: "Open the Atlas" },
  { name: "Material", title: "Get closer to the record.", copy: "Move from a name to its catalog identity, identification, age evidence, and provenance. Museum material and published occurrences keep their distinct roles.", href: "/explore?catalog=open&source=all", action: "Browse the Catalog" },
  { name: "Lineage", title: "Follow another branch.", copy: "Move through the retained classification, see evidence from each source, and explore the records within a group. A browsing hierarchy, with its source context intact.", href: "/lineage", action: "Explore Lineage" },
] as const;

export function HomeStudy() {
  const [active, setActive] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const study = studies[active];
  return <div className="home-study" data-home-reveal>
    <div className="home-study-tabs" role="tablist" aria-label="Ways to explore the evidence">
      {studies.map((item, index) => <button key={item.name} ref={element => { tabs.current[index] = element; }} id={`home-study-tab-${index}`} type="button" role="tab" aria-selected={active === index} aria-controls="home-study-panel" tabIndex={active === index ? 0 : -1} onClick={() => setActive(index)} onKeyDown={event => {
        const next = event.key === "ArrowRight" ? (index + 1) % studies.length : event.key === "ArrowLeft" ? (index + studies.length - 1) % studies.length : event.key === "Home" ? 0 : event.key === "End" ? studies.length - 1 : null;
        if (next == null) return;
        event.preventDefault();
        setActive(next);
        tabs.current[next]?.focus();
      }}><span className="study-tab-number" aria-hidden="true">0{index + 1}</span>{item.name}</button>)}
    </div>
    <div id="home-study-panel" role="tabpanel" aria-labelledby={`home-study-tab-${active}`} tabIndex={0}>
      <div className="home-study-content" key={active}>
        <div className={`home-study-drawing study-drawing-${active}`} aria-hidden="true">
          {active === 0 ? <svg viewBox="0 0 560 270" fill="none"><g className="study-contours" stroke="currentColor"><path d="M-20 160C80 30 160 140 260 55S430 25 590 10M-20 190C80 60 160 170 260 85S430 55 590 40M-20 220C80 90 160 200 260 115S430 85 590 70M-20 250C80 120 160 230 260 145S430 115 590 100M-20 280C80 150 160 260 260 175S430 145 590 130"/></g><path d="M296 44v180M205 134h182" stroke="currentColor" strokeDasharray="3 6" opacity=".45"/><circle cx="296" cy="134" r="52" stroke="currentColor" opacity=".35"/><circle className="study-location-ring" cx="296" cy="134" r="18" stroke="currentColor"/><circle cx="296" cy="134" r="5" fill="currentColor"/><path d="m316 119 40-35h83" stroke="currentColor"/><text x="362" y="73" fill="currentColor">A PLACE TO BEGIN</text></svg>
          : active === 1 ? <div className="study-accession"><span className="study-accession-label">THE SOURCE RECORD</span><span className="study-material-form" /><div className="study-accession-fields"><span>Catalog identity</span><span>Identification</span><span>Age evidence</span><span>Provenance</span></div></div>
          : <svg viewBox="0 0 560 270" fill="none"><path className="study-branch-path" d="M110 38v178h80M110 86h130v125h80M240 140h125v71h80" stroke="currentColor" strokeWidth="1.5"/>{[[110,38],[190,216],[240,86],[320,211],[365,140],[445,211]].map(([x,y])=><circle key={`${x}-${y}`} cx={x} cy={y} r="5" fill="currentColor"/>)}<g fill="currentColor"><text x="126" y="42">CLASS</text><text x="256" y="90">ORDER</text><text x="381" y="144">FAMILY</text><text x="461" y="215">GENUS</text></g></svg>}
          <span className="home-study-caption">Interface study / schematic, not a source record</span>
        </div>
        <h3>{study.title}</h3>
        <p>{study.copy}</p>
        <Link className="home-editorial-link" href={study.href}>{study.action}<span aria-hidden="true">↗</span></Link>
      </div>
    </div>
  </div>;
}
