export function formatTimeLabel(value?: string | null): string {
  const raw = String(value || "").trim();
  if (!raw) return "--";
  const normalized = raw.replace(" ", "T");
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function num(value?: number | null, digits = 2): string {
  return value == null || Number.isNaN(Number(value)) ? "--" : Number(value).toFixed(digits);
}

export function pct(value?: number | null): string {
  return value == null || Number.isNaN(Number(value)) ? "--" : `${Number(value) > 0 ? "+" : ""}${Number(value).toFixed(2)}%`;
}

export function turnover(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const normalized = Number(value);
  if (Math.abs(normalized) >= 1e8) return `${(normalized / 1e8).toFixed(2)} 亿元`;
  if (Math.abs(normalized) >= 1e4) return `${(normalized / 1e4).toFixed(2)} 万`;
  return normalized.toFixed(0);
}

export function toneClass(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "";
  return Number(value) >= 0 ? "positive" : "negative";
}

export function splitTags(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function joinTags(value?: string[] | null): string {
  return (value || []).join(", ");
}