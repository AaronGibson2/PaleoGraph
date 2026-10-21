"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api/client";
import type { DatasetStatus } from "../../lib/api/types";

/** Source totals load independently; the first screen never waits for data. */
export function HomeContext() {
  const [status, setStatus] = useState<DatasetStatus | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api.datasetStatus(controller.signal).then(setStatus).catch(() => {
      if (!controller.signal.aborted) setUnavailable(true);
    });
    return () => controller.abort();
  }, []);
  return <section className="home-context" aria-label="Current Florida evidence">
    <p className="home-scope"><span className="home-status-dot" aria-hidden="true" />Florida / retained source evidence</p>
    <dl><div><dt>UFVP material records</dt><dd>{status ? status.current_records.toLocaleString("en-US") : "UFVP"}</dd></div><div><dt>PBDB published occurrences</dt><dd>{status?.published_occurrences != null ? status.published_occurrences.toLocaleString("en-US") : "PBDB"}</dd></div><div><dt>Geography</dt><dd>Present day</dd></div></dl>
    {unavailable && <p className="home-context-note">Live totals unavailable. Browse the retained evidence in the atlas.</p>}
  </section>;
}
