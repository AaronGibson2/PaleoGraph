import type { DatasetStatus } from "../../lib/api/types.ts";

export function datasetRevision(data: DatasetStatus): string {
  return JSON.stringify([data.version, data.current_records, data.latest_scope,
    data.latest_status, data.browse_revision ?? null]);
}
