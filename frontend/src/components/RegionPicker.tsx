import { useQuery } from "@tanstack/react-query";
import { Globe2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { api, type ClientRegion, type Region } from "../lib/api";

/** All selectable regions, cached for the session. */
export function useRegions() {
  return useQuery({ queryKey: ["regions"], queryFn: api.regions, staleTime: Infinity });
}

export function regionLabel(regions: Region[] | undefined, place: ClientRegion | null | undefined) {
  if (!place) return "—";
  const r = regions?.find((x) => x.code === place.country);
  return [place.region, r?.name ?? place.country].filter(Boolean).join(", ");
}

/**
 * Country (grouped by world area) and, where tax depends on it, state or province.
 * The selected region decides the quotation currency, the tax treatment and which
 * regional procurement conventions apply.
 */
export function RegionPicker({ value, onChange, label = "Client region", compact = false }: {
  value: ClientRegion | null; onChange: (v: ClientRegion) => void; label?: string; compact?: boolean;
}) {
  const regions = useRegions();
  const list = regions.data ?? [];
  const areas = Array.from(new Set(list.map((r) => r.area)));
  const current = list.find((r) => r.code === value?.country);

  return (
    <div className="space-y-3">
      <div className={compact ? "grid grid-cols-2 gap-2" : "grid grid-cols-1 gap-3 sm:grid-cols-2"}>
        <label className="block">
          <span className="mb-1.5 block text-[12.5px] font-medium text-ink-soft">{label}</span>
          <select className="input" value={value?.country ?? ""} required
            onChange={(e) => onChange({ country: e.target.value, region: null })}>
            <option value="" disabled>Select a country…</option>
            {areas.map((area) => (
              <optgroup key={area} label={area}>
                {list.filter((r) => r.area === area).map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1.5 block text-[12.5px] font-medium text-ink-soft">State / province</span>
          <select className="input" value={value?.region ?? ""} disabled={!current?.regions.length}
            onChange={(e) => value && onChange({ country: value.country, region: e.target.value || null })}>
            <option value="">{current?.regions.length ? "From the document, or not specified" : "Not applicable"}</option>
            {current?.regions.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
      </div>
      <AnimatePresence mode="wait" initial={false}>
        {current && !compact && (
          <motion.div key={current.code} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.18 }} className="flex items-start gap-2.5 rounded-xl bg-[#f6f7f9] px-3.5 py-2.5 text-[12px] text-ink-soft">
            <Globe2 className="mt-0.5 size-3.5 shrink-0 text-muted" />
            <span>
              Quoted in <span className="font-medium text-ink">{current.currency}</span> · {current.tax}
              {current.conventions.length > 0 && <span className="text-muted"> · {current.conventions.join(" · ")}</span>}
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
