import type { Metadata } from "next";
import { ExploreWorkspace } from "../../features/explore/ExploreWorkspace";
import { parseExploreState } from "../../features/explore/state";

export const metadata: Metadata = { title: "Florida Taxonomy" };

export default async function LineagePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (typeof value === "string") params.set(key, value);
  const initial = parseExploreState(params);
  if (!params.has("surface")) initial.surface = "lineage";
  if (!initial.source && initial.surface === "lineage") initial.source = "all";
  return <ExploreWorkspace initial={initial} />;
}
