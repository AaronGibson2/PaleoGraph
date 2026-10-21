import type { ReactNode } from "react";
import "./exploration-toolbar.css";

/** A labeled, wrapping control group; controls retain their native keyboard behavior. */
export function ExplorationToolbar({ label, className = "", children }: { label: string; className?: string; children: ReactNode }) {
  return <div role="region" aria-label={label} className={`exploration-toolbar ${className}`}>{children}</div>;
}
