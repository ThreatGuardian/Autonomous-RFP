import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PricedLine } from "../../lib/types";
import { money } from "../../lib/format";

/** Horizontal price scale: cost, floor, list, every competitor and our price on one axis. */
export function PricePosition({ line, currency }: { line: PricedLine; currency: string }) {
  const offers = line.market.offers;
  const values = [line.unit_cost, line.floor_price, line.list_price, line.unit_price, ...offers.map((o) => o.unit_price_base)];
  const lo = Math.min(...values) * 0.975;
  const hi = Math.max(...values) * 1.025;
  const x = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  const marker = (v: number, label: string, cls: string, top: boolean) => (
    <div className="absolute -translate-x-1/2" style={{ left: x(v), top: top ? 0 : undefined, bottom: top ? undefined : 0 }}>
      <div className={`whitespace-nowrap text-center text-[10.5px] leading-3 ${cls}`}>{label}<div className="tnum">{money(v, currency)}</div></div>
    </div>
  );
  return (
    <div className="relative h-[112px] select-none">
      {marker(line.unit_cost, "Landed cost", "text-rose-700", true)}
      {marker(line.list_price, "List", "text-muted", true)}
      {marker(line.unit_price, "Our price", "font-semibold text-ink", false)}
      <div className="absolute inset-x-0 top-[52px] h-[6px] rounded-full bg-[#eef0f3]" />
      <div className="absolute top-[52px] h-[6px] rounded-full bg-emerald-100" style={{ left: x(line.floor_price), right: `calc(100% - ${x(line.list_price)})` }} title="Policy-compliant range" />
      <div className="absolute top-[44px] h-[22px] w-px bg-rose-600" style={{ left: x(line.unit_cost) }} />
      <div className="absolute top-[46px] h-[18px] w-px border-l border-dashed border-emerald-700" style={{ left: x(line.floor_price) }} title={`Floor ${money(line.floor_price, currency)}`} />
      <div className="absolute top-[46px] h-[18px] w-px bg-[#9aa1ad]" style={{ left: x(line.list_price) }} />
      {offers.map((o) => (
        <div key={o.competitor_id} className="group absolute top-[50px] -translate-x-1/2" style={{ left: x(o.unit_price_base) }}>
          <div className={`size-[10px] rounded-full border-2 border-white shadow ${o.unit_price_base < line.unit_cost ? "bg-rose-500" : "bg-[#6b7280]"}`} />
          <div className="pointer-events-none absolute left-1/2 top-4 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md bg-ink px-2 py-1 text-[11px] text-white group-hover:block">
            {o.competitor} · {money(o.unit_price_base, currency)}
          </div>
        </div>
      ))}
      <div className="absolute top-[45px] -translate-x-1/2" style={{ left: x(line.unit_price) }}>
        <div className="size-[14px] rotate-45 rounded-[3px] border-2 border-white bg-ink shadow" />
      </div>
    </div>
  );
}

export function WinCurve({ line, currency }: { line: PricedLine; currency: string }) {
  if (!line.curve.length) return <div className="py-8 text-center text-[12.5px] text-muted">No market reference — curve not available.</div>;
  const data = line.curve.map((p) => ({ ...p, win: Math.round(p.win_probability * 1000) / 10 }));
  return (
    <div className="h-[220px]">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
          <CartesianGrid stroke="#eef0f3" vertical={false} />
          <XAxis dataKey="unit_price" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v) => money(v, currency, { compact: true })}
            tick={{ fontSize: 10.5, fill: "#9aa1ad" }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="p" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10.5, fill: "#9aa1ad" }} axisLine={false} tickLine={false} width={44} />
          <YAxis yAxisId="e" orientation="right" hide />
          <Tooltip
            contentStyle={{ borderRadius: 8, border: "1px solid #e6e8ec", fontSize: 12 }}
            labelFormatter={(v) => `Unit price ${money(Number(v), currency)}`}
            formatter={(v, name) => (name === "Win probability" ? [`${v}%`, name] : [money(Number(v), currency), name])}
          />
          <Area yAxisId="e" dataKey="expected_profit" name="Expected profit" stroke="#c98a1b" fill="#fbf3e4" strokeWidth={1.5} type="monotone" />
          <Line yAxisId="p" dataKey="win" name="Win probability" stroke="#0b1220" strokeWidth={2} dot={false} type="monotone" />
          <ReferenceLine yAxisId="p" x={line.unit_price} stroke="#0b1220" strokeDasharray="3 3" label={{ value: "Recommended", position: "insideTopRight", fontSize: 10.5, fill: "#0b1220" }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
