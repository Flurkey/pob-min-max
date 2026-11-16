export function formatStat(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Number.isInteger(value)) return new Intl.NumberFormat("en-US").format(value);
  return String(value);
}

export function formatDelta(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const text = formatStat(value);
  return value > 0 ? `+${text}` : text;
}

export function formatWhen(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

const LABELS: Record<string, string> = {
  import: "Imported",
  copy: "Working copy",
  equipment: "Equipment edit",
  passive: "Passive edit",
  save: "Saved",
};

export function revisionLabel(label: string): string {
  return LABELS[label] ?? label;
}
