import type { ExpressionSpecification } from "maplibre-gl";
import { createMap, maplibregl, tileUrl } from "./basemap";
import { facilityStops, type Measure } from "../facilities";
import { snapshots } from "../data";
import { fmt, monthIndex, monthLabel, timeScale } from "../format";

const NO_FACILITY = "#cbd2db";
const FRAME_MS = 1400;
const last = snapshots.length - 1;
const x = timeScale(snapshots[0].date, snapshots[last].date);

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const root = $("timelapse");
const playButton = $<HTMLButtonElement>("tl-play");
const slider = $<HTMLInputElement>("tl-slider");
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");

const state = { measure: "any" as Measure, i: last, playing: false };
let timer = 0;
let mapReady = false;

// Without WebGL the chart and controls still work.
let map: ReturnType<typeof createMap> | undefined;
try {
  map = createMap("tl-map", { cooperativeGestures: true, dragRotate: false });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.touchZoomRotate.disableRotation();
} catch {
  $("tl-nomap").hidden = false;
}

const width = (z10: number, z16: number): ExpressionSpecification => [
  "interpolate",
  ["exponential", 1.5],
  ["zoom"],
  10,
  z10,
  16,
  z16,
];

const color = (key: string) =>
  ["match", ["get", key], ...facilityStops(state.measure), NO_FACILITY] as unknown as ExpressionSpecification;

function render() {
  const { i, measure } = state;
  const snap = snapshots[i];
  const low = measure === "low_stress";
  root.dataset.measure = measure;

  if (map && mapReady) {
    const key = snap.key;
    for (const id of ["history-casing", "history-lines"]) map.setFilter(id, ["has", key]);
    map.setPaintProperty("history-lines", "line-color", color(key));
  }

  $("tl-date").textContent = monthLabel(snap.date);
  $("tl-miles").textContent = fmt(low ? snap.low_stress_miles : snap.any_miles, 1);
  $("tl-miles-kind").textContent = low ? "miles of protected lane or greenway" : "miles with a bike facility";
  $("tl-pct").textContent = `${fmt(low ? snap.low_stress_pct : snap.any_pct, 1)}%`;
  const rate = snap.miles_per_year?.[low ? "low_stress" : "any"];
  $("tl-velocity").textContent =
    rate == null
      ? "Earliest archived copy of the city's data."
      : `Added ${fmt(rate, 1)} miles a year since ${monthLabel(snapshots[i - 1].date)}.`;

  document.querySelectorAll<HTMLElement>("#tl-chart [data-i]").forEach((el) => {
    const n = Number(el.dataset.i);
    el.dataset.state = n === i ? "current" : n < i ? "past" : "future";
    el.setAttribute("aria-pressed", String(n === i));
  });
  document.querySelectorAll<HTMLElement>("#tl-chart .cursor").forEach((el) => {
    el.style.left = `${x(snap.date)}%`;
  });
  slider.value = String(monthIndex(snap.date));
  slider.setAttribute("aria-valuetext", monthLabel(snap.date));
  $("tl-prev").toggleAttribute("disabled", i === 0);
  $("tl-next").toggleAttribute("disabled", i === last);
  $("tl-readout").setAttribute("aria-live", state.playing ? "off" : "polite");
}

function go(i: number) {
  state.i = Math.min(last, Math.max(0, i));
  render();
}

function stop() {
  state.playing = false;
  clearTimeout(timer);
  playButton.textContent = "Play";
  playButton.setAttribute("aria-pressed", "false");
  render();
}

function tick() {
  if (state.i >= last) return stop();
  go(state.i + 1);
  timer = window.setTimeout(tick, FRAME_MS);
}

function play() {
  state.playing = true;
  playButton.textContent = "Pause";
  playButton.setAttribute("aria-pressed", "true");
  if (state.i >= last) state.i = 0;
  render();
  timer = window.setTimeout(tick, FRAME_MS);
}

// A user move always takes over from playback.
const pick = (i: number) => {
  if (state.playing) stop();
  go(i);
};

playButton.addEventListener("click", () => (state.playing ? stop() : play()));
$("tl-prev").addEventListener("click", () => pick(state.i - 1));
$("tl-next").addEventListener("click", () => pick(state.i + 1));
$("tl-chart").addEventListener("click", (event) => {
  const target = (event.target as HTMLElement).closest<HTMLElement>("[data-i]");
  if (target) pick(Number(target.dataset.i));
});

// The slider is on the calendar like the chart, so a drag snaps to the nearest snapshot.
slider.addEventListener("input", () => {
  const v = Number(slider.value);
  let best = 0;
  snapshots.forEach((s, n) => {
    if (Math.abs(monthIndex(s.date) - v) < Math.abs(monthIndex(snapshots[best].date) - v)) best = n;
  });
  pick(best);
});
slider.addEventListener("keydown", (event) => {
  const moves: Record<string, number> = {
    ArrowLeft: state.i - 1,
    ArrowDown: state.i - 1,
    ArrowRight: state.i + 1,
    ArrowUp: state.i + 1,
    Home: 0,
    End: last,
  };
  if (event.key in moves) {
    event.preventDefault();
    pick(moves[event.key]);
  }
});

$("tl-measure").addEventListener("change", (event) => {
  state.measure = (event.target as HTMLInputElement).value as Measure;
  render();
});

function motionPreference() {
  // Stepping stays available; only the animation goes.
  playButton.hidden = reduceMotion.matches;
  if (reduceMotion.matches && state.playing) stop();
}
reduceMotion.addEventListener("change", motionPreference);
motionPreference();

map?.on("load", () => {
  if (!map) return;
  map.addSource("history", {
    type: "vector",
    url: tileUrl("history.pmtiles"),
    attribution: '<a href="https://data.cityofchicago.org">City of Chicago</a>',
  });
  const layer = { type: "line", source: "history", "source-layer": "history" } as const;
  const layout = { "line-cap": "round", "line-join": "round" } as const;
  map.addLayer({
    ...layer,
    id: "history-casing",
    layout,
    paint: { "line-color": "#ffffff", "line-width": width(2.6, 9) },
  });
  map.addLayer({
    ...layer,
    id: "history-lines",
    layout,
    paint: { "line-color": color(snapshots[state.i].key), "line-width": width(1.4, 6) },
  });
  mapReady = true;
  render();
});

render();
