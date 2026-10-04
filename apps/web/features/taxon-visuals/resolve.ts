import { mammaliaId, taxonomicVisualRules } from "./rules.ts";
import type { ResolvedTaxonVisual } from "./types.ts";

const rules = new Map(taxonomicVisualRules.map(rule => [rule.id, rule]));

/** Source membership only. Path is self/identification first, then nearest parents.
 * Missing context is neutral; labels never determine membership.
 */
export function resolveTaxonVisual(input: { id?: string; classification_path_ids?: readonly string[] }): ResolvedTaxonVisual {
  const path = input.classification_path_ids?.length ? input.classification_path_ids : input.id ? [input.id] : [];
  for (const [depth, id] of path.entries()) {
    const rule = rules.get(id);
    if (rule && "neutral" in rule) return { kind: "neutral" };
    if (rule && "archetype" in rule && (depth === 0 || rule.inherit)) return { kind: "archetype", archetype: rule.archetype };
    if (id === mammaliaId) return { kind: "generic", visual: "mammal" };
  }
  return { kind: "neutral" };
}
