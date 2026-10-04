export type AnimalArchetype = "armadillo" | "lagomorph" | "rodent" | "bat" | "sirenian" | "proboscidean" | "terrestrial-ungulate" | "turtle" | "snake" | "crocodilian" | "bony-fish" | "bird" | "frog" | "shark";
export type ResolvedTaxonVisual = { kind: "archetype"; archetype: AnimalArchetype } | { kind: "generic"; visual: "mammal" } | { kind: "neutral" };
