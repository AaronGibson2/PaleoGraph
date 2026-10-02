import type { Metadata } from "next";
import { ExploreWorkspace } from "../../features/explore/ExploreWorkspace";
import { parseExploreState } from "../../features/explore/state";

export const metadata: Metadata = { title: "Explore" };

export default async function ExplorePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (typeof value === "string") params.set(key, value);
  return <ExploreWorkspace initial={parseExploreState(params)} />;
}
