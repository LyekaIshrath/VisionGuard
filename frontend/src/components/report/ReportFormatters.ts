// Shared formatters for Work Session Intelligence Report

export function formatDuration(seconds?: number | null): string {
  if (seconds == null || isNaN(seconds) || seconds < 0) return "—";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const rem = s % 60;
    if (rem === 0) return `${m}m 00s`;
    return `${m}m ${rem < 10 ? '0' : ''}${rem}s`;
  }
  const h = Math.floor(s / 3600);
  const remM = Math.floor((s % 3600) / 60);
  return `${h}h ${remM < 10 ? '0' : ''}${remM}m`;
}

export function formatPct(val?: number | null, fallback = "—"): string {
  if (val == null || isNaN(val)) return fallback;
  const clamped = Math.max(0, val);
  const rounded = Math.round(clamped * 10) / 10;
  if (Number.isInteger(rounded)) {
    return `${rounded}%`;
  }
  return `${rounded.toFixed(1)}%`;
}

export function formatSafeDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function formatSafeTime(iso?: string | null, includeSeconds = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    ...(includeSeconds ? { second: "2-digit" } : {}),
  });
}

export function formatTimeRange(startIso?: string | null, endIso?: string | null): string {
  const s = formatSafeTime(startIso);
  const e = formatSafeTime(endIso);
  if (s === "—" && e === "—") return "—";
  if (e === "—") return `${s} — (Active)`;
  return `${s} — ${e}`;
}
