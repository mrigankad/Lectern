import type { ChartSpec } from "@/lib/types";

/**
 * Slide charts, drawn to scale in canvas pixels (the slide is 1920 x 1080).
 * The data, the chart kind and the series colours all come from the scene graph, so this
 * only decides marks: thin bars with a gap, 5px lines, recessive grid, labels in ink.
 */

type Ink = { text: string; soft: string; grid: string; base: string; surface: string };

const FS = 24; // label size in canvas px (12pt once exported)

/** A round step so that about four gridlines cover the value. */
function niceStep(v: number): number {
  if (v <= 0) return 1;
  const raw = v / 4;
  const pow = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / pow;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * pow;
}

function fmt(v: number, unit?: string): string {
  const abs = Math.abs(v);
  let s: string;
  if (abs >= 1_000_000) s = `${+(v / 1_000_000).toFixed(1)}M`;
  else if (abs >= 10_000) s = `${+(v / 1_000).toFixed(0)}k`;
  else if (abs >= 1_000) s = `${+(v / 1_000).toFixed(1)}k`;
  else s = String(+v.toFixed(abs < 10 ? 1 : 0));
  if (!unit) return s;
  if (unit === "$" || unit === "€" || unit === "£") return `${unit}${s}`;
  return unit.length <= 2 ? `${s}${unit}` : `${s} ${unit}`;
}

function color(colors: string[], i: number): string {
  return colors.length ? colors[i % colors.length] : "#16181D";
}

function Legend({ names, colors, ink, x, y }: { names: string[]; colors: string[]; ink: Ink; x: number; y: number }) {
  let cursor = x;
  return (
    <g>
      {names.map((name, i) => {
        const at = cursor;
        cursor += 34 + name.length * FS * 0.56 + 36;
        return (
          <g key={`${name}-${i}`} transform={`translate(${at} ${y})`}>
            <rect width={20} height={20} rx={5} y={-17} fill={color(colors, i)} />
            <text x={32} fontSize={FS} fill={ink.soft}>
              {name}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function Cartesian({ chart, w, h, ink }: { chart: ChartSpec; w: number; h: number; ink: Ink }) {
  const { kind, categories, series, colors, unit } = chart;
  const n = Math.max(1, categories.length);
  const all = series.flatMap((s) => s.values.slice(0, n)).filter((v) => Number.isFinite(v));
  const dataMax = Math.max(0, ...all);
  const dataMin = Math.min(0, ...all);
  const step = niceStep(Math.max(dataMax, -dataMin));
  const top = Math.max(step, Math.ceil(dataMax / step - 1e-9) * step);
  const bottom = dataMin < 0 ? -Math.ceil(-dataMin / step - 1e-9) * step : 0;
  const multi = series.length > 1;
  const compact = h < 260; // small chart boxes: drop the value axis

  const padL = compact ? 8 : 26 + fmt(top, unit).length * FS * 0.58;
  const padR = 28;
  const padT = (multi ? FS + 30 : 14) + (kind === "bar" ? 0 : 20);
  const padB = FS + 30;
  const pw = Math.max(10, w - padL - padR);
  const ph = Math.max(10, h - padT - padB);
  const yOf = (v: number) => padT + ph - ((v - bottom) / (top - bottom || 1)) * ph;
  const ticks = Array.from({ length: Math.round((top - bottom) / step) + 1 }, (_, i) => bottom + i * step);
  const band = pw / n;
  // Skip category labels that would collide.
  const longest = Math.max(1, ...categories.map((c) => c.length));
  const every = Math.max(1, Math.ceil((longest * FS * 0.56 + 20) / band));

  return (
    <>
      {multi ? <Legend names={series.map((s) => s.name)} colors={colors} ink={ink} x={padL} y={FS} /> : null}
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={padL} x2={padL + pw} y1={yOf(t)} y2={yOf(t)} stroke={Math.abs(t) < 1e-9 ? ink.base : ink.grid} strokeWidth={Math.abs(t) < 1e-9 ? 3 : 2} />
          {compact ? null : (
            <text x={padL - 16} y={yOf(t) + FS * 0.35} fontSize={FS} textAnchor="end" fill={ink.soft}>
              {fmt(t, unit)}
            </text>
          )}
        </g>
      ))}
      {categories.map((c, i) =>
        i % every === 0 ? (
          <text key={`${c}-${i}`} x={padL + band * (i + 0.5)} y={padT + ph + FS + 14} fontSize={FS} textAnchor="middle" fill={ink.soft}>
            {c}
          </text>
        ) : null,
      )}

      {kind === "bar"
        ? (() => {
            const groupW = band * 0.68;
            const gap = 6;
            const bw = Math.max(4, (groupW - gap * (series.length - 1)) / Math.max(1, series.length));
            const labelBars = !multi && n <= 8 && bw > 60;
            return series.map((s, si) =>
              s.values.slice(0, n).map((v, i) => {
                const x = padL + band * i + (band - groupW) / 2 + si * (bw + gap);
                const y0 = yOf(0);
                const y1 = yOf(v);
                const r = Math.min(8, bw / 2, Math.abs(y1 - y0));
                const up = v >= 0;
                const path = up
                  ? `M${x} ${y0}V${y1 + r}Q${x} ${y1} ${x + r} ${y1}H${x + bw - r}Q${x + bw} ${y1} ${x + bw} ${y1 + r}V${y0}Z`
                  : `M${x} ${y0}V${y1 - r}Q${x} ${y1} ${x + r} ${y1}H${x + bw - r}Q${x + bw} ${y1} ${x + bw} ${y1 - r}V${y0}Z`;
                return (
                  <g key={`${si}-${i}`}>
                    <path d={path} fill={color(colors, si)} />
                    {labelBars ? (
                      <text x={x + bw / 2} y={up ? y1 - 12 : y1 + FS + 6} fontSize={FS} fontWeight={700} textAnchor="middle" fill={ink.text}>
                        {fmt(v, unit)}
                      </text>
                    ) : null}
                  </g>
                );
              }),
            );
          })()
        : series.map((s, si) => {
            const pts = s.values.slice(0, n).map((v, i) => [padL + band * (i + 0.5), yOf(v)] as const);
            if (!pts.length) return null;
            const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join("");
            const last = pts[pts.length - 1];
            const c = color(colors, si);
            return (
              <g key={si}>
                {kind === "area" ? (
                  <path d={`${line}L${last[0]} ${yOf(0)}L${pts[0][0]} ${yOf(0)}Z`} fill={c} opacity={0.14} />
                ) : null}
                <path d={line} fill="none" stroke={c} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
                <circle cx={last[0]} cy={last[1]} r={10} fill={c} stroke={ink.surface} strokeWidth={4} />
                {!multi ? (
                  <text x={last[0]} y={last[1] - 24} fontSize={FS} fontWeight={700} textAnchor="end" fill={ink.text}>
                    {fmt(s.values[pts.length - 1], unit)}
                  </text>
                ) : null}
              </g>
            );
          })}
    </>
  );
}

function Pie({ chart, w, h, ink }: { chart: ChartSpec; w: number; h: number; ink: Ink }) {
  const values = (chart.series[0]?.values ?? []).map((v) => Math.max(0, v || 0));
  const total = values.reduce((a, b) => a + b, 0) || 1;
  const legendW = Math.min(w * 0.45, 520);
  const r = Math.max(10, Math.min((w - legendW) / 2, h / 2) - 12);
  const cx = r + 12;
  const cy = h / 2;
  let angle = -Math.PI / 2;
  const rowH = FS + 22;
  const startY = cy - (values.length * rowH) / 2 + FS;
  return (
    <>
      {values.map((v, i) => {
        const a0 = angle;
        const a1 = angle + (v / total) * Math.PI * 2;
        angle = a1;
        const large = a1 - a0 > Math.PI ? 1 : 0;
        const full = values.length === 1 || v === total;
        const d = full
          ? `M${cx - r} ${cy}A${r} ${r} 0 1 1 ${cx + r} ${cy}A${r} ${r} 0 1 1 ${cx - r} ${cy}Z`
          : `M${cx} ${cy}L${cx + r * Math.cos(a0)} ${cy + r * Math.sin(a0)}A${r} ${r} 0 ${large} 1 ${cx + r * Math.cos(a1)} ${cy + r * Math.sin(a1)}Z`;
        // The surface-coloured stroke is the gap between slices.
        return <path key={i} d={d} fill={color(chart.colors, i)} stroke={ink.surface} strokeWidth={4} strokeLinejoin="round" />;
      })}
      {values.map((v, i) => (
        <g key={`l-${i}`} transform={`translate(${cx + r + 56} ${startY + i * rowH})`}>
          <rect width={20} height={20} rx={5} y={-17} fill={color(chart.colors, i)} />
          <text x={32} fontSize={FS} fill={ink.soft}>
            {chart.categories[i] ?? `Part ${i + 1}`}
          </text>
          <text x={legendW - 70} fontSize={FS} fontWeight={700} textAnchor="end" fill={ink.text}>
            {Math.round((v / total) * 100)}%
          </text>
        </g>
      ))}
    </>
  );
}

export function ChartSvg({ chart, w, h, dark, surface }: { chart: ChartSpec; w: number; h: number; dark: boolean; surface: string }) {
  const ink: Ink = dark
    ? { text: "#FFFFFF", soft: "#C9CBD3", grid: "#3A3D46", base: "#FFFFFF", surface }
    : { text: "#16181D", soft: "#5E6370", grid: "#E8E8EC", base: "#16181D", surface };
  const label = `${chart.kind} chart: ${chart.series.map((s) => s.name).join(", ")}`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label} style={{ display: "block", overflow: "visible" }}>
      {chart.kind === "pie" ? <Pie chart={chart} w={w} h={h} ink={ink} /> : <Cartesian chart={chart} w={w} h={h} ink={ink} />}
    </svg>
  );
}
