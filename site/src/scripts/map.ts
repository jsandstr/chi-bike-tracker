import * as maplibregl from "maplibre-gl";
import type { ExpressionSpecification, GeoJSONSource } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { Protocol } from "pmtiles";
import type { Feature, FeatureCollection, Position } from "geojson";
import wardsUrl from "../../../data/processed/wards.geojson?url";
import communityAreasUrl from "../../../data/processed/community_areas.geojson?url";
import { BREAKS, FACILITIES, RAMP, type Measure } from "../facilities";

type Kind = "wards" | "community_areas";
type View = "streets" | "areas";
type AreaProps = { id: string; name: string; any_pct: number; low_stress_pct: number };
type Areas = FeatureCollection<GeoJSON.Geometry, AreaProps>;

const NO_FACILITY = "#cbd2db";
const MUTED_FACILITY = "#9aa4b2";
const INK = "#14213a";
const SELECTED = "#2563eb";
const AREA_BORDER = "#d98a3d";
const CHICAGO: [number, number, number, number] = [-87.94, 41.644, -87.524, 42.023];

const state = { measure: "any" as Measure, kind: "wards" as Kind, view: "streets" as View };
let selected: string | null = null;

const titleCase = (s: string) => s.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase());
const areaName = (p: AreaProps) => (state.kind === "wards" ? `Ward ${p.name}` : titleCase(p.name));
const pct = (n: number) => `${n.toFixed(1)}%`;

// The library cannot find its own worker once Vite has bundled it.
maplibregl.setWorkerUrl(workerUrl);
maplibregl.addProtocol("pmtiles", new Protocol().tile);

const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  bounds: CHICAGO,
  fitBoundsOptions: { padding: 24 },
  minZoom: 8,
  maxBounds: [-88.6, 41.2, -86.9, 42.5],
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });

const areas: Record<Kind, Promise<Areas>> = {
  wards: fetch(wardsUrl).then((r) => r.json()),
  community_areas: fetch(communityAreasUrl).then((r) => r.json()),
};

function bikewayColor(): ExpressionSpecification {
  if (state.view === "areas") return ["literal", INK] as unknown as ExpressionSpecification;
  const stops = FACILITIES.flatMap((f) => [
    f.name,
    state.measure === "low_stress" && !f.lowStress ? MUTED_FACILITY : f.color,
  ]);
  return ["match", ["get", "facility"], ...stops, NO_FACILITY] as unknown as ExpressionSpecification;
}

function width(z10: number, z16: number): ExpressionSpecification {
  return ["interpolate", ["exponential", 1.5], ["zoom"], 10, z10, 16, z16];
}

function areaFill(): ExpressionSpecification {
  const breaks = BREAKS[state.measure];
  const steps = breaks.flatMap((b, i) => [b, RAMP[i + 1]]);
  return ["step", ["get", `${state.measure}_pct`], RAMP[0], ...steps] as ExpressionSpecification;
}

function bounds(feature: Feature): [number, number, number, number] {
  const box: [number, number, number, number] = [180, 90, -180, -90];
  const visit = (c: Position | Position[] | Position[][] | Position[][][]): void => {
    if (typeof c[0] === "number") {
      const [x, y] = c as Position;
      box[0] = Math.min(box[0], x);
      box[1] = Math.min(box[1], y);
      box[2] = Math.max(box[2], x);
      box[3] = Math.max(box[3], y);
    } else {
      (c as Position[]).forEach(visit);
    }
  };
  if ("coordinates" in feature.geometry) visit(feature.geometry.coordinates);
  return box;
}

function select(id: string | null) {
  const ready = Boolean(map.getSource("areas"));
  if (selected && ready) map.setFeatureState({ source: "areas", id: selected }, { selected: false });
  selected = id;
  if (id && ready) map.setFeatureState({ source: "areas", id }, { selected: true });
  document.querySelectorAll<HTMLButtonElement>("#ranking button").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.id === id));
  });
}

async function renderRanking() {
  const data = await areas[state.kind];
  const key = `${state.measure}_pct` as const;
  const rows = data.features.map((f) => f.properties).sort((a, b) => b[key] - a[key]);
  const max = Math.max(...rows.map((r) => r[key]), 1);
  const list = document.getElementById("ranking")!;
  list.replaceChildren(
    ...rows.map((row, i) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.id = row.id;
      button.setAttribute("aria-pressed", String(row.id === selected));
      button.innerHTML =
        `<span class="rank">${i + 1}</span><span class="name"></span>` +
        `<span class="track"><span class="fill" style="width:${(100 * row[key]) / max}%"></span></span>` +
        `<span class="pct">${pct(row[key])}</span>`;
      button.querySelector(".name")!.textContent = areaName(row);
      button.addEventListener("click", () => {
        const feature = data.features.find((f) => f.properties.id === row.id)!;
        select(row.id);
        map.fitBounds(bounds(feature), { padding: 48, maxZoom: 13.5 });
      });
      li.append(button);
      return li;
    }),
  );
}

function renderRampLabels() {
  const b = BREAKS[state.measure];
  const labels = [`under ${b[0]}%`, ...b.slice(0, -1).map((lo, i) => `${lo}–${b[i + 1]}%`), `${b.at(-1)}%+`];
  document.getElementById("ramp-labels")!.replaceChildren(
    ...labels.map((text) => Object.assign(document.createElement("span"), { textContent: text })),
  );
}

async function apply() {
  document.body.dataset.measureActive = state.measure;
  document.querySelectorAll<HTMLElement>(".headline").forEach((el) => {
    el.hidden = el.dataset.measure !== state.measure;
  });
  document.getElementById("ramp")!.hidden = state.view !== "areas";
  renderRampLabels();
  await renderRanking();
  if (!map.getLayer("bikeways")) return;
  map.setPaintProperty("bikeways", "line-color", bikewayColor());
  // Over the area colours the network is context only, so it recedes.
  const receded = state.view === "areas";
  map.setPaintProperty("bikeways", "line-opacity", receded ? 0.45 : 1);
  map.setPaintProperty("bikeways", "line-width", receded ? width(0.6, 3) : width(1.4, 6));
  map.setLayoutProperty("bikeways-casing", "visibility", receded ? "none" : "visible");
  map.setPaintProperty("area-fill", "fill-color", areaFill());
  map.setLayoutProperty("area-fill", "visibility", state.view === "areas" ? "visible" : "none");
  // A warm outline separates neighbouring areas of the same blue class.
  map.setPaintProperty("area-outline", "line-color", receded ? AREA_BORDER : INK);
  map.setPaintProperty("area-outline", "line-width", receded ? 1 : 0.6);
  map.setPaintProperty("area-outline", "line-opacity", receded ? 0.6 : 0.35);
}

async function setKind() {
  select(null);
  (map.getSource("areas") as GeoJSONSource | undefined)?.setData(await areas[state.kind]);
}

for (const name of ["measure", "view", "kind"] as const) {
  document.getElementById(name)!.addEventListener("change", async (event) => {
    (state[name] as string) = (event.target as HTMLInputElement).value;
    if (name === "kind") await setKind();
    await apply();
  });
}

map.on("load", async () => {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  map.addSource("streets", {
    type: "vector",
    url: `pmtiles://${location.origin}${base}/tiles/streets.pmtiles`,
    attribution: '<a href="https://data.cityofchicago.org">City of Chicago</a>',
  });
  map.addSource("areas", { type: "geojson", data: await areas[state.kind], promoteId: "id" });

  const isBikeway: ExpressionSpecification = ["has", "facility"];
  const isSelected: ExpressionSpecification = ["boolean", ["feature-state", "selected"], false];

  map.addLayer({
    id: "area-fill",
    type: "fill",
    source: "areas",
    layout: { visibility: "none" },
    paint: { "fill-color": areaFill(), "fill-opacity": 0.82 },
  });
  // Always present, so an area can be clicked in either view; only the selected one is tinted.
  map.addLayer({
    id: "area-selected",
    type: "fill",
    source: "areas",
    paint: { "fill-color": SELECTED, "fill-opacity": ["case", isSelected, 0.2, 0] },
  });
  map.addLayer({
    id: "streets-plain",
    type: "line",
    source: "streets",
    "source-layer": "streets",
    filter: ["!", isBikeway],
    layout: { "line-cap": "round" },
    paint: { "line-color": NO_FACILITY, "line-width": width(0.4, 3), "line-opacity": 0.9 },
  });
  map.addLayer({
    id: "area-outline",
    type: "line",
    source: "areas",
    paint: { "line-color": INK, "line-width": 0.6, "line-opacity": 0.35 },
  });
  map.addLayer({
    id: "bikeways-casing",
    type: "line",
    source: "streets",
    "source-layer": "streets",
    filter: isBikeway,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#ffffff", "line-width": width(2.6, 9) },
  });
  map.addLayer({
    id: "bikeways",
    type: "line",
    source: "streets",
    "source-layer": "streets",
    filter: isBikeway,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": bikewayColor(), "line-width": width(1.4, 6) },
  });
  // Invisible wide line so thin bikeways are easy to hover and tap.
  map.addLayer({
    id: "bikeways-hit",
    type: "line",
    source: "streets",
    "source-layer": "streets",
    filter: isBikeway,
    paint: { "line-color": "#000", "line-opacity": 0, "line-width": 16 },
  });

  map.on("mousemove", (event) => {
    const [street] = map.queryRenderedFeatures(event.point, { layers: ["bikeways-hit"] });
    const [area] = map.queryRenderedFeatures(event.point, { layers: ["area-fill"] });
    let html = "";
    if (street) {
      const facility = FACILITIES.find((f) => f.name === street.properties.facility);
      html = `<b>${street.properties.name || "Unnamed street"}</b>${facility?.label ?? ""}`;
    } else if (area) {
      const p = area.properties as AreaProps;
      html = `<b>${areaName(p)}</b>${pct(p.any_pct)} any facility<br>${pct(p.low_stress_pct)} protected or greenway`;
    }
    map.getCanvas().style.cursor = html ? "pointer" : "";
    if (html) popup.setLngLat(event.lngLat).setHTML(html).addTo(map);
    else popup.remove();
  });
  map.on("mouseout", () => popup.remove());
  map.on("click", "area-selected", (event) => {
    const id = event.features?.[0]?.properties.id;
    if (id) {
      select(String(id));
      document.querySelector(`#ranking button[data-id="${CSS.escape(String(id))}"]`)?.scrollIntoView({ block: "nearest" });
    }
  });

  await apply();
});

apply();
