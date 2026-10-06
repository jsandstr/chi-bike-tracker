import history from "../../data/processed/history.json";
import policyData from "../../data/processed/policies.json";

// The JSON imports infer unions that are awkward to narrow, so the shapes are stated here.
export type Snapshot = {
  key: string;
  date: string;
  any_miles: number;
  low_stress_miles: number;
  any_pct: number;
  low_stress_pct: number;
  by_facility: Record<string, number>;
  miles_per_year: { any: number; low_stress: number } | null;
};

export type Target = {
  label: string;
  metric: "none" | "any_miles_added" | "any_miles_total" | "protected_miles_total";
  value: number | null;
  note?: string | null;
  reported?: { value: number; as_of: string; source: string } | null;
  measured: number | null;
  progress: number | null;
};

export type Contribution = {
  from: string;
  to: string;
  truncated: boolean;
  any_miles: number;
  low_stress_miles: number;
  any_pct_points: number;
  by_facility: Record<string, number>;
};

export type Policy = {
  id: string;
  name: string;
  kind: "plan" | "program" | "ordinance" | "pledge";
  jurisdiction: string;
  status: "active" | "completed" | "expired" | "failed";
  start: string;
  end: string | null;
  summary: string;
  targets: Target[];
  sources: { title: string; url: string }[];
  contribution: Contribution | null;
};

export const snapshots = history.snapshots as Snapshot[];
export const STREET_MILES = history.street_miles;
export const policies = policyData as unknown as Policy[];

export const KIND_LABEL: Record<Policy["kind"], string> = {
  plan: "Plan",
  program: "Program",
  ordinance: "Ordinance",
  pledge: "Pledge",
};

export const STATUS_LABEL: Record<Policy["status"], string> = {
  active: "Active",
  completed: "Completed",
  expired: "Expired, goal not met",
  failed: "Failed",
};
