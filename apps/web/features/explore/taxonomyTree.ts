import type { TaxonomyNode, TaxonomyPage } from "../../lib/api/taxonomy.ts";

export type Branch = { page?: TaxonomyPage; loading?: boolean; error?: string };
export type TreeRow = { node: TaxonomyNode; level: number; position: number; size: number };
export function flattenTree(roots: TaxonomyNode[], branches: Readonly<Record<string, Branch>>, expanded: ReadonlySet<string>): TreeRow[] {
  const rows: TreeRow[] = [];
  const seen = new Set<string>();
  const visit = (nodes: TaxonomyNode[], level: number, total: number) => nodes.forEach((node, index) => {
    if (seen.has(node.id)) return;
    seen.add(node.id);
    rows.push({ node, level, position: index + 1, size: total });
    if (expanded.has(node.id)) visit(branches[node.id]?.page?.items ?? [], level + 1, branches[node.id]?.page?.total ?? 0);
  });
  visit(roots, 1, roots.length);
  return rows;
}
export function taxonomyContext(context: string): string {
  const params = new URLSearchParams(context);
  params.delete("q"); params.delete("cursor"); params.delete("offset");
  if (!params.has("source")) params.set("source", "all");
  params.set("limit", "100"); params.sort();
  return params.toString();
}
export function treeWindow(length: number, scrollTop: number, height = 560, rowHeight = 58) {
  if (length <= 120) return { start: 0, end: length, before: 0, after: 0 };
  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - 8);
  const end = Math.min(length, start + Math.ceil(height / rowHeight) + 16);
  return { start, end, before: start * rowHeight, after: Math.max(0, length - end) * rowHeight };
}
export function treeIndent(level: number, deepestVisibleLevel: number): number {
  // Keep the last ten visible levels distinct even on a 50-level provider path.
  const omittedUpperLevels = Math.max(0, deepestVisibleLevel - 11);
  return Math.min(10, Math.max(0, level - 1 - omittedUpperLevels)) * 19 + 8;
}
export function adjacentRow(rows: readonly TreeRow[], id: string, key: string): string | undefined {
  const index = rows.findIndex(row => row.node.id === id);
  if (key === "Home") return rows[0]?.node.id;
  if (key === "End") return rows.at(-1)?.node.id;
  if (key === "ArrowDown") return rows[Math.min(rows.length - 1, index + 1)]?.node.id;
  if (key === "ArrowUp") return rows[Math.max(0, index - 1)]?.node.id;
  return undefined;
}
