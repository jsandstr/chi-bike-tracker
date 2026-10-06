import * as maplibregl from "maplibre-gl";
import type { MapOptions } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { Protocol } from "pmtiles";
import { CHICAGO } from "../facilities";
import { basePath } from "../format";

export { maplibregl };

// The library cannot find its own worker once Vite has bundled it.
maplibregl.setWorkerUrl(workerUrl);
maplibregl.addProtocol("pmtiles", new Protocol().tile);

export const tileUrl = (file: string) => `pmtiles://${location.origin}${basePath()}/tiles/${file}`;

export function createMap(container: string, options: Partial<MapOptions> = {}) {
  return new maplibregl.Map({
    container,
    style: "https://tiles.openfreemap.org/styles/positron",
    bounds: CHICAGO,
    fitBoundsOptions: { padding: 24 },
    minZoom: 8,
    maxBounds: [-88.6, 41.2, -86.9, 42.5],
    attributionControl: { compact: true },
    ...options,
  });
}
