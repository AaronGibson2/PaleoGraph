"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { AgeRange, TimeConfiguration } from "../../lib/api/types";
import { ageLabel } from "../explore/state";

type Props = { age: AgeRange; configuration: TimeConfiguration; onChange: (age: AgeRange) => void };
type Boundary = "older_ma" | "younger_ma";
type Drag = { pointer: number; x: number; value: number; maximum: number; width: number };
const format = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 2 });

export function TimeControl({ age: committed, configuration, onChange }: Props) {
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
  const choose = (next: AgeRange) => {
    if (timer.current) clearTimeout(timer.current);
    pending.current = null;
    setDraft(null);
    onChange(next);
  };
  // Keep an extended URL range's scale steady while either handle moves.
  const [scaleMaximum, setScaleMaximum] = useState(Math.max(configuration.max_ma, age.older_ma ?? 0));
  const maximum = Math.max(scaleMaximum, configuration.max_ma, age.older_ma ?? 0);
  const allAges = age.older_ma === null;
  const older = age.older_ma ?? maximum;
  const younger = age.younger_ma ?? 0;
  const position = (value: number) => (1 - value / maximum) * 100;
  const change = (boundary: Boundary, value: number, keyboard = false) => {
    const rounded = Math.round(value * 100) / 100;
    const next = boundary === "older_ma"
      ? { older_ma: Math.max(younger, Math.min(maximum, rounded)), younger_ma: younger }
      : { older_ma: older, younger_ma: Math.max(0, Math.min(older, rounded)) };
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
    setScaleMaximum(maximum);
    drag.current = { pointer: event.pointerId, x: event.clientX, value, maximum, width: track.current.getBoundingClientRect().width };
  };
  const move = (event: PointerEvent<HTMLButtonElement>, boundary: Boundary) => {
    const active = drag.current;
    if (!active || active.pointer !== event.pointerId) return;
    change(boundary, active.value - (event.clientX - active.x) / active.width * active.maximum);
  };
  const keyboard = (event: KeyboardEvent<HTMLButtonElement>, boundary: Boundary, value: number) => {
    const step = event.shiftKey ? 0.1 : 0.01;
    const values: Record<string, number> = {
      ArrowLeft: value + step, ArrowRight: value - step,
      ArrowUp: value + step, ArrowDown: value - step,
      PageUp: value + 1, PageDown: value - 1,
      Home: boundary === "older_ma" ? younger : 0,
      End: boundary === "older_ma" ? maximum : older,
    };
    if (!(event.key in values)) return;
    event.preventDefault();
    setScaleMaximum(maximum);
    change(boundary, values[event.key], true);
  };
  return <section className="time-control" aria-labelledby="time-heading">
    <div className="time-title">
      <div><p className="eyebrow">Selected time</p><h2 id="time-heading">{allAges ? "All ages" : ageLabel(age)}</h2></div>
      <p className="time-explanation">{draft ? "Previewing range · map updates when you finish." : allAges ? "Every mapped assertion, including unknown ages." : "Map shows overlapping known ages. Unknown and partial ages excluded."}</p>
      <button className="quiet-button" aria-pressed={allAges} onClick={() => { setScaleMaximum(configuration.max_ma); choose({ older_ma: null, younger_ma: null }); }}>All ages</button>
    </div>
    <div className="time-direction"><span>← Older</span><span>Millions of years before present</span><span>Present →</span></div>
    <div className="time-instrument" data-all-ages={allAges}>
      <div className="time-track" ref={track}>
        <div className="time-strata" aria-hidden="true">
          {configuration.windows.map((window, index) => <span key={window.label} className={`time-stratum time-window-${index}`} style={{ left: `${position(window.older_ma)}%`, width: `${(window.older_ma - window.younger_ma) / maximum * 100}%` }} />)}
        </div>
        <div className="time-selection" aria-hidden="true" style={{ left: `${position(older)}%`, width: `${(older - younger) / maximum * 100}%` }} />
        {(["older_ma", "younger_ma"] as const).map(boundary => {
          const value = boundary === "older_ma" ? older : younger;
          const x = position(value);
          return <button key={boundary} type="button" role="slider"
            className={`time-handle ${boundary === "older_ma" ? "time-handle-older" : "time-handle-younger"}`}
            style={{ left: `${x}%` }} data-edge={x < 12 ? "start" : x > 88 ? "end" : "middle"}
            aria-label={boundary === "older_ma" ? "Older age bound" : "Younger age bound"}
            aria-orientation="horizontal" aria-valuenow={value}
            aria-valuemin={boundary === "older_ma" ? younger : 0}
            aria-valuemax={boundary === "older_ma" ? maximum : older}
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
      <div className="time-windows" aria-label="Demo age window presets">
        {configuration.windows.map((window, index) => <button key={window.label} className={`time-window time-window-${index}`}
          aria-pressed={age.older_ma === window.older_ma && age.younger_ma === window.younger_ma}
          onClick={() => { setScaleMaximum(configuration.max_ma); choose({ older_ma: window.older_ma, younger_ma: window.younger_ma }); }}
        >{window.label}</button>)}
      </div>
    </div>
    <p className="time-footnote">Numeric demo windows · not a formal geological timescale</p>
    <p id="time-help" className="time-help">Drag either boundary. Arrow keys adjust by 0.01 Ma; Shift by 0.1 Ma. Left is older, right is younger. Page keys adjust by 1 Ma; Home/End move to the allowed limits.</p>
  </section>;
}
