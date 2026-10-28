"use client";

import { useState } from "react";
import type { OpeningPhase } from "./useOpeningMotion";

type Layer = "all" | "strata" | "life" | "evidence";
const layers = [
  { id: "strata", label: "Strata", description: "Time, held in layers." },
  { id: "life", label: "Life", description: "Life leaves an impression." },
  { id: "evidence", label: "Evidence", description: "A trace becomes a record. A record opens an atlas." },
] as const;

type Props = { phase: OpeningPhase; enhanced: boolean; artFailed: boolean; onReplay: () => void; onFinish: () => void };

export function OpeningScene({ phase, enhanced, artFailed, onReplay, onFinish }: Props) {
  const [active, setActive] = useState<Layer>("all");
  return <div className="opening-scene" data-phase={phase} data-focus={active} data-art={artFailed ? "fallback" : "ready"}>
    <div className="opening-world" role="img" aria-label="An imagined stratified Florida landform with illustrated life impressions, evidence connections, and the PaleoGraph molar-and-atlas emblem. Artistic composition, not a geological reconstruction or record-location map.">
      <div className="opening-scroll-depth">
      <svg className="opening-fallback" viewBox="0 0 1000 850" aria-hidden="true"><path d="m72 60 196 8 17 43 170 22 67 28 131 2 12-32 45 18 29 49 10 80 49 69 15 70 37 65 35 63 21 66-5 63-34 40-34-10-30-46-17-69-34-71-9-63-36-39-39-78-17-66-56-45-45 9-40-31-44-5-32-29-50-2-36-28-50 3-19-42-86-8Z"/><path d="m830 764-37 18-40 9-38-4m-15-2-23-6" fill="none"/></svg>
      <div className="opening-depth opening-art-depth">
        <div className="opening-uncover-window">
        <picture className="opening-art-picture">
          <source media="(max-width: 700px)" srcSet="/home/atlas-beneath-mobile.avif" type="image/avif" />
          <source media="(max-width: 700px)" srcSet="/home/atlas-beneath-mobile.webp" type="image/webp" />
          <source srcSet="/home/atlas-beneath-desktop.avif" type="image/avif" />
          {/* A responsive native picture selects one artwork without a JS gate. */}
          <img className="opening-art" src="/home/atlas-beneath-desktop.webp" width="1536" height="1024" fetchPriority="high" alt="" />
        </picture>
        </div>
      </div>
      <div className="opening-depth opening-traces-depth" aria-hidden="true">
        <svg className="opening-traces opening-traces-desktop" viewBox="0 0 1000 850" fill="none">
          <g className="opening-geography"><path pathLength="1" d="M150 147Q310 195 490 183T787 267Q850 350 863 436T925 626" /><path pathLength="1" d="M162 163Q330 218 505 202T771 282Q832 355 847 445T910 638" /><path pathLength="1" d="M177 179Q344 238 521 224T754 298Q813 365 831 458T894 651" /></g>
          <g className="opening-strata-traces"><path pathLength="1" d="M203 250Q360 320 534 300T831 438" /><path pathLength="1" d="M214 267Q362 340 536 318T820 456" /><path pathLength="1" d="M225 284Q370 357 542 337T810 473" /><path pathLength="1" d="M748 510Q813 541 881 551" /><path pathLength="1" d="M755 530Q818 560 891 573" /></g>
          <g className="opening-evidence-traces"><path pathLength="1" d="M682 359C578 366 548 530 380 633" /><path pathLength="1" d="M783 504C649 517 596 628 428 675" /><path pathLength="1" d="M856 618C760 704 582 748 435 728" /><path pathLength="1" d="M283 668Q251 682 254 716" /></g>
          <g className="opening-evidence-nodes"><circle cx="682" cy="359" r="4"/><circle cx="783" cy="504" r="4"/><circle cx="856" cy="618" r="4"/><circle cx="380" cy="633" r="3"/><circle cx="428" cy="675" r="3"/><circle cx="435" cy="728" r="3"/></g>
        </svg>
        <svg className="opening-traces opening-traces-mobile" viewBox="0 0 600 800" fill="none" preserveAspectRatio="none"><g className="opening-geography"><path pathLength="1" d="M50 100Q175 157 334 160T487 324L529 546" /><path pathLength="1" d="M55 115Q174 177 328 179T472 337L515 559" /></g><g className="opening-strata-traces"><path pathLength="1" d="M77 206Q180 257 307 243T470 374" /><path pathLength="1" d="M82 222Q194 278 317 264T461 391" /></g><g className="opening-evidence-traces"><path pathLength="1" d="M379 320C276 351 231 453 176 580" /><path pathLength="1" d="M452 450C360 475 308 613 219 638" /></g></svg>
      </div>
      <div className="opening-depth opening-life-depth" aria-hidden="true"><span className="opening-impression opening-impression-proboscidean" /><span className="opening-impression opening-impression-crocodilian" /><span className="opening-impression opening-impression-shark" /></div>
      <div className="opening-field-note opening-note-time" aria-hidden="true"><span>01 / Deep time</span><i /><small>Held in layers</small></div>
      <div className="opening-field-note opening-note-life" aria-hidden="true"><span>02 / Life</span><i /><small>An impression remains</small></div>
      <div className="opening-field-note opening-note-evidence" aria-hidden="true"><span>03 / Evidence</span><i /><small>A trace becomes a record</small></div>
      <div className="opening-brand-construction" aria-hidden="true"><div className="opening-brand-bands">{Array.from({ length: 12 }, (_, index) => <i key={index} style={{ animationDelay: `${1400 + index * 40}ms` }} />)}</div><span>PaleoGraph</span><small>A record. An open world.</small></div>
      </div>
    </div>
    <div className="opening-scene-footer">
      <div className="opening-controls" role="group" aria-label="Highlight a layer of the opening illustration"><span className="opening-controls-label">Explore a layer</span>{layers.map((layer, index) => <button type="button" key={layer.id} disabled={!enhanced} aria-pressed={active === layer.id} onClick={() => { onFinish(); setActive(active === layer.id ? "all" : layer.id); }}><span aria-hidden="true">0{index + 1}</span>{layer.label}</button>)}<button className="opening-replay" type="button" disabled={!enhanced} aria-label="Replay the opening illustration" onClick={() => { setActive("all"); onReplay(); }}>↻</button></div>
      <p className="opening-layer-caption" aria-live="polite">{layers.find(layer => layer.id === active)?.description ?? "An atlas beneath the surface."}</p>
      <p className="opening-art-credit">An imagined geological landscape / an invitation to the evidence.</p>
    </div>
  </div>;
}
