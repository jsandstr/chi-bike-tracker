const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const fmt = (n: number, digits = 0) =>
  n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

// "2014-12" -> "Dec 2014"
export const monthLabel = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
};

export const monthIndex = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return y * 12 + m;
};

// Snapshots are unevenly spaced, so every x position goes through the calendar, never the array index.
export const timeScale = (first: string, last: string) => (ym: string) =>
  (100 * (monthIndex(ym) - monthIndex(first))) / (monthIndex(last) - monthIndex(first));

export const signed = (n: number, digits = 1) => `${n < 0 ? "−" : "+"}${fmt(Math.abs(n), digits)}`;

export const basePath = () => import.meta.env.BASE_URL.replace(/\/$/, "");
