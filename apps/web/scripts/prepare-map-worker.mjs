import { copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

// Next emits URL imports as individual assets, losing the worker's sibling import.
// Serve the installed pair together. See MapLibre's Next.js installation guide.
const destination = new URL("../public/maplibre/", import.meta.url);
await mkdir(destination, { recursive: true });
for (const filename of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  await copyFile(fileURLToPath(import.meta.resolve(`maplibre-gl/dist/${filename}`)), new URL(filename, destination));
}
