"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { AgeRange, TimeConfiguration } from "../../lib/api/types";
import { ageLabel, formatMa } from "../explore/state";

type Props = { age: AgeRange; configuration: TimeConfiguration; focus?: string; onFocus: (id: string) => void; onChange: (age: AgeRange, interval?: string) => void };
type Boundary = "older_ma" | "younger_ma";
type Drag = { pointer: number; x: number; value: number; maximum: number; width: number };
const format = formatMa;

export function TimeControl({ age: committed, configuration, focus, onFocus, onChange }: Props) {
  const track = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pending = useRef<AgeRange | null>(null);
  const ageKey = `${committed.older_ma}:${committed.younger_ma}`;
  const [draft, setDraft] = useState<{ base: string; age: AgeRange } | null>(null);
  if (draft && draft.base !== ageKey) setDraft(null);
  const age = draft?.base === ageKey ? draft.age : committed;
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
    pending.current = null;
    drag.current = null;
  }, [ageKey]);
  const finish = () => {
    if (timer.current) clearTimeout(timer.current);
    const next = pending.current;
    pending.current = null;
    setDraft(null);
    if (next) onChange(next);
  };
  const choose = (next: AgeRange, interval?: string) => {
    if (timer.current) clearTimeout(timer.current);
    pending.current = null;
    setDraft(null);
    onChange(next, interval);
  };
  const focused = configuration.units.find(unit => unit.id === focus) ?? configuration.units.find(unit => unit.name === "Cenozoic")!;
  const maximum = Math.max(focused.older_ma, committed.older_ma ?? 0);
  const minimum = Math.min(focused.younger_ma, committed.younger_ma ?? focused.younger_ma);
  const span = maximum - minimum;
  const allAges = age.older_ma === null;
  const older = age.older_ma ?? maximum;
  const younger = age.younger_ma ?? minimum;
  const position = (value: number) => Math.max(0, Math.min(100, (maximum - value) / span * 100));
  const children = configuration.units.filter(unit => unit.parent === focused.id && unit.rank !== "Subepoch").sort((a, b) => b.older_ma - a.older_ma);
  const presets = configuration.units.filter(unit => unit.parent === focused.id && unit.rank === "Subepoch");
  const ancestry = [];
  let ancestor = focused;
  while (ancestor) { ancestry.unshift(ancestor); ancestor = configuration.units.find(unit => unit.id === ancestor.parent)!; }
  const change = (boundary: Boundary, value: number, keyboard = false) => {
    const step = span < 0.1 ? 0.0001 : span < 5 ? 0.001 : 0.01;
    const rounded = Number((Math.round(value / step) * step).toFixed(4));
    const next = boundary === "older_ma"
      ? { older_ma: Math.max(Math.max(minimum, Math.min(maximum, younger)), Math.min(maximum, rounded)), younger_ma: Math.max(minimum, Math.min(maximum, younger)) }
      : { older_ma: Math.max(minimum, Math.min(maximum, older)), younger_ma: Math.max(minimum, Math.min(Math.min(maximum, older), rounded)) };
    pending.current = next;
    setDraft({ base: ageKey, age: next });
    if (timer.current) clearTimeout(timer.current);
    if (keyboard) timer.current = setTimeout(finish, 250);
  };
  const start = (event: PointerEvent<HTMLButtonElement>, value: number) => {
    if (!event.isPrimary || event.button !== 0 || !track.current) return;
    event.preventDefault();
    event.currentTarget.focus({ preventScroll: true });
    event.currentTarget.setPointerCapture(event.pointerId);
    if (timer.current) clearTimeout(timer.current);
    drag.current = { pointer: event.pointerId, x: event.clientX, value: Math.max(minimum, Math.min(maximum, value)), maximum: span, width: track.current.getBoundingClientRect().width };
  };
  const move = (event: PointerEvent<HTMLButtonElement>, boundary: Boundary) => {
    const active = drag.current;
    if (!active || active.pointer !== event.pointerId) return;
    change(boundary, active.value - (event.clientX - active.x) / active.width * active.maximum);
  };
  const keyboard = (event: KeyboardEvent<HTMLButtonElement>, boundary: Boundary, value: number) => {
    const step = (span < 0.1 ? 0.0001 : span < 5 ? 0.001 : 0.01) * (event.shiftKey ? 10 : 1);
    const values: Record<string, number> = {
      ArrowLeft: value + step, ArrowRight: value - step,
      ArrowUp: value + step, ArrowDown: value - step,
      PageUp: value + span / 10, PageDown: value - span / 10,
      Home: boundary === "older_ma" ? Math.max(minimum, younger) : minimum,
      End: boundary === "older_ma" ? maximum : older,
    };
    if (!(event.key in values)) return;
    event.preventDefault();
    change(boundary, values[event.key], true);
  };
  return <section className="time-control" aria-labelledby="time-heading">
    <div className="time-title">
      <div><p className="eyebrow">Selected time</p><h2 id="time-heading">{allAges ? "All ages" : ageLabel(age)}</h2></div>
      <p className="time-explanation" title="A complete material envelope overlaps the selected closed range when its younger bound is no older than the selection's older bound, and its older bound is no younger than the selection's younger bound. Equality counts; missing bounds are excluded only when filtering.">{draft ? "Previewing range · map updates when you finish." : allAges ? "All current material, including unresolved ages." : "Material envelopes overlapping this range, including boundary equality. Unresolved numeric ages excluded."}</p>
      <button className="quiet-button" aria-pressed={allAges} onClick={() => { choose({ older_ma: null, younger_ma: null }); }}>All ages</button>
    </div>
    <nav className="time-ancestry" aria-label="Timescale depth"><button onClick={() => onFocus("ics:2026-06:Phanerozoic")}>Deep time</button>{ancestry.map(unit => <button key={unit.id} aria-current={unit.id === focused.id ? "location" : undefined} onClick={() => onFocus(unit.id)}>{unit.name} <small>{unit.rank}</small></button>)}</nav>
    <div className="time-direction"><span>← Older</span><span>Millions of years before present</span><span>Present →</span></div>
    <div className="time-instrument" data-all-ages={allAges}>
      <div className="time-track" ref={track}>
        <div className="time-strata" aria-hidden="true">
          {children.map(unit => <span key={unit.id} className="time-stratum" style={{ left: `${position(unit.older_ma)}%`, width: `${(unit.older_ma - unit.younger_ma) / span * 100}%`, background: unit.color }} />)}
        </div>
        <div className="time-selection" aria-hidden="true" style={{ left: `${position(older)}%`, width: `${(Math.min(maximum, older) - Math.max(minimum, younger)) / span * 100}%` }} />
        {(["older_ma", "younger_ma"] as const).map(boundary => {
          const value = boundary === "older_ma" ? older : younger;
          const x = position(value);
          return <button key={boundary} type="button" role="slider"
            className={`time-handle ${boundary === "older_ma" ? "time-handle-older" : "time-handle-younger"}`}
            style={{ left: `${x}%` }} data-edge={x < 12 ? "start" : x > 88 ? "end" : "middle"}
            aria-label={boundary === "older_ma" ? "Older age bound" : "Younger age bound"}
            aria-orientation="horizontal" aria-valuenow={Math.max(minimum, Math.min(maximum, value))}
            aria-valuemin={boundary === "older_ma" ? younger : minimum}
            aria-valuemax={boundary === "older_ma" ? maximum : Math.min(maximum, Math.max(minimum, older))}
            aria-valuetext={`${format(value)} million years before present${allAges ? "; all ages currently included" : ""}`}
            aria-describedby="time-help"
            onPointerDown={event => start(event, value)} onPointerMove={event => move(event, boundary)}
            onPointerUp={event => { if (drag.current?.pointer === event.pointerId) { move(event, boundary); drag.current = null; finish(); event.currentTarget.releasePointerCapture(event.pointerId); } }}
            onPointerCancel={() => { drag.current = null; finish(); }} onLostPointerCapture={() => { if (drag.current) { drag.current = null; finish(); } }}
            onKeyDown={event => keyboard(event, boundary, value)} onBlur={() => { if (!drag.current) finish(); }}>
            <span className="time-handle-label" aria-hidden="true">{format(value)} <small>Ma</small></span>
            <span className="time-grip" aria-hidden="true" />
          </button>;
        })}
      </div>
      <div className="time-windows" aria-label={`${focused.name} interval selections`}>
        {[...children, ...presets].map(unit => <div key={unit.id} className="interval-choice" style={{ "--interval-color": unit.color } as React.CSSProperties}>
          <button className="time-window" aria-pressed={age.older_ma === unit.older_ma && age.younger_ma === unit.younger_ma} onClick={() => choose({ older_ma: unit.older_ma, younger_ma: unit.younger_ma }, unit.id)}><strong>{unit.name}</strong><small>{format(unit.older_ma)}–{format(unit.younger_ma)} Ma</small></button>
          {configuration.units.some(child => child.parent === unit.id) && <button className="interval-dive" aria-label={`Explore subdivisions of ${unit.name}`} onClick={() => onFocus(unit.id)}>↓</button>}
        </div>)}
      </div>
    </div>
    <div className="time-bottom"><p className="time-footnote"><a href={configuration.source_url} target="_blank" rel="noopener noreferrer" title={configuration.attribution}>ICS v{configuration.version.replace("-", "/")}</a> / CGMW · © ICS 2026 · <a href={configuration.license_url}>CC BY 4.0</a> · PaleoGraph adaptation with two PDF-supported corrections; no endorsement. Reference calibration, not measured specimen ages.</p><p id="time-help" className="time-help">Drag boundaries. Arrows adjust the range; Shift ×10. Left is older. Page keys step 10%; Home/End reach limits.</p></div>
  </section>;
}
