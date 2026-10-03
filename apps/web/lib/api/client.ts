import type { AgeRange, DatasetStatus, MapResponse, OccurrenceDetail, TimeConfiguration, Viewport } from "./types.ts";

const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  code: string;
  constructor(message: string, code = "NETWORK_ERROR") {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

export async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { signal, headers: { Accept: "application/json" }, cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.error?.message ?? "Occurrence data could not be loaded.", body?.error?.code ?? "HTTP_ERROR");
  }
  return response.json() as Promise<T>;
}

export function occurrenceQuery(viewport: Viewport, age: AgeRange): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(viewport)) params.set(key, String(value));
  if (age.older_ma !== null && age.younger_ma !== null) {
    params.set("older_ma", String(age.older_ma));
    params.set("younger_ma", String(age.younger_ma));
  }
  params.set("limit", "200");
  return params.toString();
}

export const api = {
  occurrences: (query: string, signal?: AbortSignal) => request<MapResponse>(`/map/occurrences?${query}`, signal),
  occurrence: (id: string, signal?: AbortSignal) => request<OccurrenceDetail>(`/occurrences/${encodeURIComponent(id)}`, signal),
  timeConfiguration: (signal?: AbortSignal) => request<TimeConfiguration>("/time-intervals", signal),
  datasetStatus: (signal?: AbortSignal) => request<DatasetStatus>("/datasets/ufvp", signal),
};
