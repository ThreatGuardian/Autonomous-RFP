const cache = new Map<string, Intl.NumberFormat>();

function nf(key: string, make: () => Intl.NumberFormat) {
  let f = cache.get(key);
  if (!f) {
    f = make();
    cache.set(key, f);
  }
  return f;
}

export function money(value: number | null | undefined, currency = "INR", opts: { decimals?: number; compact?: boolean } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const locale = currency === "INR" ? "en-IN" : "en-US";
  const decimals = opts.decimals ?? (Math.abs(value) >= 1000 ? 0 : 2);
  if (opts.compact) {
    if (currency === "INR") {
      const abs = Math.abs(value);
      if (abs >= 1e7) return `₹${(value / 1e7).toFixed(2)} Cr`;
      if (abs >= 1e5) return `₹${(value / 1e5).toFixed(2)} L`;
      // Indian compact notation has no thousands suffix; show the full amount.
      return nf("en-IN-INR-0", () => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 })).format(value);
    }
    return nf(`${locale}-${currency}-c`, () => new Intl.NumberFormat(locale, { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 })).format(value);
  }
  return nf(`${locale}-${currency}-${decimals}`, () =>
    new Intl.NumberFormat(locale, { style: "currency", currency, minimumFractionDigits: decimals, maximumFractionDigits: decimals }),
  ).format(value);
}

export const pct = (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? "—" : `${v.toFixed(digits)}%`);
export const prob = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
export const num = (v: number) => new Intl.NumberFormat("en-IN").format(v);

export function date(value: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return new Intl.DateTimeFormat("en-GB", opts).format(d);
}

export function relative(value: string) {
  const diff = (Date.now() - new Date(value).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return date(value);
}

export function daysUntil(value: string | null) {
  if (!value) return null;
  const d = new Date(`${value}T23:59:59`);
  return Math.ceil((d.getTime() - Date.now()) / 86_400_000);
}

export function duration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const CATEGORY_LABEL: Record<string, string> = {
  laptop: "Notebooks", desktop: "Desktops", workstation: "Workstations", monitor: "Monitors", network_switch: "Switching",
  wireless: "Wireless", firewall: "Security", router: "Routing", server: "Servers", storage: "Storage", storage_media: "Drives",
  power: "Power", rack: "Racks", cabling: "Cabling", peripheral: "Peripherals", printer: "Printers", av: "Projectors & AV",
  audio: "Headsets & audio", component: "Components",
  software: "Software", service: "Services",
};
