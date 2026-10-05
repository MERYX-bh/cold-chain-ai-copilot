import { useMemo } from "react";
import { STATIONS, TEMP_FLOOR_C, TEMP_LIMIT_C, routeFor, temperatureAt, temperatureStatus, type Scenario } from "../lib/route";

type Props = { scenario: Scenario; fractions: number[]; progress: number };

const W = 900;
const H = 180;
const PAD = { left: 52, right: 24, top: 18, bottom: 34 };
const Y_MIN = -1;
const Y_MAX = 9;

const x = (p: number) => PAD.left + p * (W - PAD.left - PAD.right);
const y = (t: number) => PAD.top + (1 - (t - Y_MIN) / (Y_MAX - Y_MIN)) * (H - PAD.top - PAD.bottom);

export function TemperatureChart({ scenario, fractions, progress }: Props) {
  const points = useMemo(() => routeFor(scenario), [scenario]);
  const line = useMemo(() => {
    const samples = [];
    for (let p = 0; p <= 1.0001; p += 0.005) samples.push(`${x(p).toFixed(1)},${y(temperatureAt(p, scenario, fractions)).toFixed(1)}`);
    return samples.join(" ");
  }, [scenario, fractions]);

  const now = temperatureAt(progress, scenario, fractions);
  const status = temperatureStatus(now);

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cargo temperature along the journey compared with the 0 to 4 degree limit">
      <title>Temperature along the journey</title>
      <rect className="chart-band" x={PAD.left} y={y(TEMP_LIMIT_C)} width={W - PAD.left - PAD.right} height={y(TEMP_FLOOR_C) - y(TEMP_LIMIT_C)} />
      {[0, 4, 8].map((tick) => (
        <g key={tick}>
          <line className="chart-grid" x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} />
          <text className="chart-axis" x={PAD.left - 10} y={y(tick) + 4} textAnchor="end">
            {tick} °C
          </text>
        </g>
      ))}
      <line className="chart-limit" x1={PAD.left} x2={W - PAD.right} y1={y(TEMP_LIMIT_C)} y2={y(TEMP_LIMIT_C)} />
      <text className="chart-limit-label" x={W - PAD.right} y={y(TEMP_LIMIT_C) - 6} textAnchor="end">
        SOP limit 4.0 °C
      </text>

      {points.map((point, index) => (
        <g key={`${point.id}-${index}`}>
          <line className="chart-tick" x1={x(fractions[index] ?? 0)} x2={x(fractions[index] ?? 0)} y1={PAD.top} y2={H - PAD.bottom} />
          <text className="chart-axis" x={x(fractions[index] ?? 0)} y={H - 10} textAnchor="middle">
            {point.id === "junction" ? "Fork" : STATIONS[point.id].short}
          </text>
        </g>
      ))}

      <polyline className="chart-line" points={line} />
      <line className="chart-cursor" x1={x(progress)} x2={x(progress)} y1={PAD.top} y2={H - PAD.bottom} />
      <circle className={`chart-dot chart-dot--${status}`} cx={x(progress)} cy={y(now)} r="6" />
    </svg>
  );
}
