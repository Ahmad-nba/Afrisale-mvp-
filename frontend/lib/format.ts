export function formatPrice(value: number | null | undefined): string {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return "0";
  return numeric.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function stockBadgeColor(label: "in" | "low" | "out"): string {
  switch (label) {
    case "out":
      return "bg-rose-100 text-rose-700 border-rose-200";
    case "low":
      return "bg-amber-100 text-amber-800 border-amber-200";
    default:
      return "bg-emerald-100 text-emerald-700 border-emerald-200";
  }
}

export function stockBadgeText(label: "in" | "low" | "out", total: number): string {
  if (label === "out") return "Out of stock";
  if (label === "low") return `Low: ${total} left`;
  return `In stock: ${total}`;
}
