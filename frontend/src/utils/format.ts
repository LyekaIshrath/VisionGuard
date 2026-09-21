export function formatSafeTime(timestamp?: string | number | Date | null): string {
  if (!timestamp) return "--";
  try {
    const d = new Date(timestamp);
    return isNaN(d.getTime()) ? "--" : d.toLocaleTimeString();
  } catch {
    return "--";
  }
}

export function formatDuration(sec?: number | null): string {
  if (sec == null || isNaN(sec)) return "--";
  const s = Math.round(sec);
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (hrs > 0) return `${hrs}h ${mins}m ${secs}s`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

export function formatPercent(val?: number | null): string {
  if (val == null || isNaN(val)) return "--";
  return `${Math.round(val)}%`;
}
