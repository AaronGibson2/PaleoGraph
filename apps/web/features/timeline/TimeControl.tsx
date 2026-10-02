"use client";

import type { AgeRange, TimeConfiguration } from "../../lib/api/types";
import { ageLabel } from "../explore/state";

type Props = { age: AgeRange; configuration: TimeConfiguration; onChange: (age: AgeRange) => void };

export function TimeControl({ age, configuration, onChange }: Props) {
  const allAges = age.older_ma === null;
  const older = age.older_ma ?? configuration.max_ma;
  const younger = age.younger_ma ?? 0;
  const maximum = Math.max(configuration.max_ma, older);
  return <section className="time-control" aria-labelledby="time-heading">
    <div className="time-title">
      <div><p className="eyebrow">Geological time</p><h2 id="time-heading">{allAges ? "All ages" : ageLabel(age)}</h2></div>
      <p className="time-explanation">{allAges ? "Includes unknown and partly known ages." : "Overlapping known ages. Unknown ages excluded."}</p>
      <button className="quiet-button" aria-pressed={allAges} onClick={() => onChange({ older_ma: null, younger_ma: null })}>All ages</button>
    </div>
    <div className="time-direction"><span>← Older</span><span>Millions of years before present</span><span>Present →</span></div>
    <div className="time-windows" aria-label="Demo age windows">
      {configuration.windows.map((window, index) => <button
        key={window.label} className={`time-window time-window-${index}`}
        aria-pressed={age.older_ma === window.older_ma && age.younger_ma === window.younger_ma}
        onClick={() => onChange({ older_ma: window.older_ma, younger_ma: window.younger_ma })}
      >{window.label}</button>)}
    </div>
    <div className="range-controls">
      <label>Older bound <span>{older} Ma</span>
        <input type="range" min={0} max={maximum} step={0.01} value={older}
          aria-label="Older age bound" aria-valuetext={`${older} million years before present`}
          onChange={event => onChange({ older_ma: Number(event.target.value), younger_ma: Math.min(younger, Number(event.target.value)) })} />
      </label>
      <label>Younger bound <span>{younger} Ma</span>
        <input type="range" min={0} max={maximum} step={0.01} value={younger}
          aria-label="Younger age bound" aria-valuetext={`${younger} million years before present`}
          onChange={event => onChange({ older_ma: Math.max(older, Number(event.target.value)), younger_ma: Number(event.target.value) })} />
      </label>
    </div>
    <p className="time-footnote">Numeric demo windows · not a formal geological timescale</p>
  </section>;
}
