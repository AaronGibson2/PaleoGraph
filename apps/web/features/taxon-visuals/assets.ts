import type { AnimalArchetype } from "./types.ts";

/** Static normalized alpha masks; originals are archived outside public/. */
export const archetypeAssets: Record<AnimalArchetype, { src: string }> = {
  "armadillo": { src: "/taxonomy/silhouettes/armadillo.png" },
  "lagomorph": { src: "/taxonomy/silhouettes/lagomorph.png" },
  "rodent": { src: "/taxonomy/silhouettes/rodent.png" },
  "bat": { src: "/taxonomy/silhouettes/bat.png" },
  "sirenian": { src: "/taxonomy/silhouettes/sirenian.png" },
  "proboscidean": { src: "/taxonomy/silhouettes/proboscidean.png" },
  "terrestrial-ungulate": { src: "/taxonomy/silhouettes/terrestrial-ungulate.png" },
  "turtle": { src: "/taxonomy/silhouettes/turtle.png" },
  "snake": { src: "/taxonomy/silhouettes/snake.png" },
  "crocodilian": { src: "/taxonomy/silhouettes/crocodilian.png" },
  "bony-fish": { src: "/taxonomy/silhouettes/bony-fish.png" },
  "bird": { src: "/taxonomy/silhouettes/bird.png" },
  "frog": { src: "/taxonomy/silhouettes/frog.png" },
  "shark": { src: "/taxonomy/silhouettes/shark.png" },
};
