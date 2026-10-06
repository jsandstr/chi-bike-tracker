// Order and names match FACILITY_RANK in pipeline/src/pipeline/coverage/match.py.
// Colours were checked for colour-blind separation across all pairs on the map surface.
export const FACILITIES = [
  { name: "Protected Bike Lane", label: "Protected bike lane", color: "#008300", lowStress: true },
  { name: "Neighborhood Greenway", label: "Neighborhood greenway", color: "#1baf7a", lowStress: true },
  { name: "Buffered Bike Lane", label: "Buffered bike lane", color: "#4a3aa7", lowStress: false },
  { name: "Bike Lane", label: "Painted bike lane", color: "#2a78d6", lowStress: false },
  { name: "Marked Shared Lane", label: "Shared lane marking", color: "#eda100", lowStress: false },
] as const;

export type Measure = "any" | "low_stress";

// One hue, light to dark. Upper bounds of the first four classes, in percent.
export const RAMP = ["#e3ecf6", "#b5cde8", "#7ba6d6", "#3d7cc0", "#17508f"];
export const BREAKS: Record<Measure, number[]> = {
  any: [5, 10, 15, 20],
  low_stress: [2, 5, 8, 12],
};

export const MUTED_FACILITY = "#9aa4b2";
export const CHICAGO: [number, number, number, number] = [-87.94, 41.644, -87.524, 42.023];

// Flat [name, colour, ...] pairs for a MapLibre "match"; non-low-stress facilities fade under the low-stress measure.
export const facilityStops = (measure: Measure) =>
  FACILITIES.flatMap((f) => [f.name, measure === "low_stress" && !f.lowStress ? MUTED_FACILITY : f.color]);
