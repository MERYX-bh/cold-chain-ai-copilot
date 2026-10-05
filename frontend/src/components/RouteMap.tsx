import { useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  CONGESTION_LIMIT,
  STATIONS,
  portCongestion,
  routeFor,
  smoothPath,
  stationFractions,
  temperatureAt,
  temperatureStatus,
  type Scenario,
  type StationId,
} from "../lib/route";
import { toolInfo } from "../lib/toolInfo";

type Props = {
  scenario: Scenario;
  progress: number;
  activeTool?: string | null;
  compact?: boolean;
  onFractions?: (fractions: number[]) => void;
};

type RealStation = Exclude<StationId, "junction">;
const WIDTH = 900;

function Glyph({ id }: { id: RealStation }) {
  switch (id) {
    case "producer":
      return (
        <g className="glyph">
          <path d="M-7 5 C-7 -6 2 -8 8 -8 C8 -1 5 7 -7 5 Z" />
          <path d="M-7 5 L3 -3" />
        </g>
      );
    case "cold":
      return (
        <g className="glyph">
          <path d="M0 -9V9 M-8 -4.5L8 4.5 M8 -4.5L-8 4.5" />
        </g>
      );
    case "port":
      return (
        <g className="glyph">
          <rect x="-8" y="-1" width="7" height="6" />
          <rect x="1" y="-1" width="7" height="6" />
          <rect x="-4" y="-8" width="8" height="6" />
        </g>
      );
    case "depot":
      return (
        <g className="glyph">
          <path d="M-9 8V-2L0 -8L9 -2V8Z" />
          <path d="M-3 8V2H3V8" />
        </g>
      );
    case "dc":
      return (
        <g className="glyph">
          <path d="M-8 -4L0 -8L8 -4V5L0 9L-8 5Z" />
          <path d="M-8 -4L0 0L8 -4M0 0V9" />
        </g>
      );
    case "store":
      return (
        <g className="glyph">
          <path d="M-9 -2L-7 -8H7L9 -2Z" />
          <path d="M-7 -2V8H7V-2" />
          <path d="M-2 8V3H2V8" />
        </g>
      );
  }
}

function ToolChip({ tool, x, y, compact }: { tool: string; x: number; y: number; compact: boolean }) {
  const text = toolInfo(tool).chip;
  const width = text.length * (compact ? 13 : 7.6) + (compact ? 56 : 44);
  const height = compact ? 40 : 30;
  const cx = Math.min(Math.max(x, width / 2 + 8), WIDTH - width / 2 - 8);
  const cy = y > 270 ? y - 78 : y + 52;
  return (
    <g className={`chip chip--${tool}`} aria-hidden="true">
      <rect x={cx - width / 2} y={cy - height / 2} width={width} height={height} rx={height / 2} />
      <circle className="chip-dot" cx={cx - width / 2 + height / 2} cy={cy} r={compact ? 7 : 5} />
      <text x={cx - width / 2 + height} y={cy + (compact ? 8 : 4.5)}>
        {text}
      </text>
    </g>
  );
}

export function RouteMap({ scenario, progress, activeTool = null, compact = false, onFractions }: Props) {
  const points = useMemo(() => routeFor(scenario), [scenario]);
  const path = useMemo(() => smoothPath(points), [points]);
  const ghostPath = useMemo(() => smoothPath(routeFor(scenario === "congestion" ? "normal" : "congestion")), [scenario]);
  const pathRef = useRef<SVGPathElement>(null);
  const [geometry, setGeometry] = useState<{ length: number; fractions: number[] }>({ length: 1, fractions: [] });

  useLayoutEffect(() => {
    const element = pathRef.current;
    if (!element) return;
    const length = element.getTotalLength();
    const fractions = stationFractions(points, (distance) => element.getPointAtLength(distance), length);
    setGeometry({ length, fractions });
    onFractions?.(fractions);
  }, [points, path, onFractions]);

  const { length, fractions } = geometry;
  const clamped = Math.min(Math.max(progress, 0), 1);
  const here = pathRef.current && length > 1 ? pathRef.current.getPointAtLength(clamped * length) : points[0];
  const temperature = fractions.length ? temperatureAt(clamped, scenario, fractions) : 2.2;
  const status = temperatureStatus(temperature);
  const congestion = portCongestion(scenario);
  const congested = congestion > CONGESTION_LIMIT;
  const pillWidth = compact ? 104 : 70;

  const onRoute = new Map<StationId, number>();
  points.forEach((point, index) => onRoute.set(point.id, index));

  return (
    <svg className={`map ${compact ? "map--compact" : ""}`} viewBox={`0 0 ${WIDTH} 420`} role="img" aria-label="Animated map of a refrigerated shipment moving through the supply chain">
      <title>Cold-chain route</title>
      <desc>
        A truck follows the route from the packing house to the store. Its temperature is shown above it and turns red above 4 degrees Celsius.
      </desc>

      <path className="route-ghost" d={ghostPath} />
      <path ref={pathRef} className="route-base" d={path} />
      <path className="route-trail" d={path} strokeDasharray={`${length} ${length}`} strokeDashoffset={length * (1 - clamped)} />

      {(Object.keys(STATIONS) as RealStation[]).map((id) => {
        const station = STATIONS[id];
        const index = onRoute.get(id);
        const visited = index !== undefined && fractions[index] !== undefined && clamped + 1e-6 >= fractions[index];
        const avoided = index === undefined;
        const labelY = station.labelAbove ? -30 : 42;
        const placeY = station.labelAbove ? -50 : 60;
        return (
          <g key={id} transform={`translate(${station.x} ${station.y})`} className={`station ${visited ? "station--visited" : ""} ${avoided ? "station--avoided" : ""}`}>
            <circle r="20" />
            <Glyph id={id} />
            <text className="station-label" y={labelY} textAnchor="middle">
              {compact ? station.short : station.label}
            </text>
            {!compact && (
              <text className="station-place" y={placeY} textAnchor="middle">
                {station.place}
              </text>
            )}
          </g>
        );
      })}

      <g transform={`translate(${STATIONS.port.x} ${STATIONS.port.y - (compact ? 80 : 68)})`} className={`badge ${congested ? "badge--alert" : ""}`}>
        <rect x={compact ? -52 : -62} y={compact ? -18 : -12} width={compact ? 104 : 124} height={compact ? 36 : 24} rx={compact ? 18 : 12} />
        <text textAnchor="middle" y={compact ? 8 : 4.5}>
          {compact ? `Jam ${congestion.toFixed(1)}` : `Congestion ${congestion.toFixed(1)} / ${CONGESTION_LIMIT.toFixed(1)}`}
        </text>
      </g>

      <g transform={`translate(${here.x} ${here.y})`} className={`truck truck--${status}`}>
        {activeTool === "query_telemetry_db" && <circle className="ring" r="34" />}
        {status === "breach" && <circle className="pulse" r="26" />}
        <rect className="truck-body" x="-15" y="-9" width="21" height="15" rx="2" />
        <rect className="truck-cab" x="7" y="-5" width="9" height="11" rx="2" />
        <circle className="truck-wheel" cx="-8" cy="8" r="3.2" />
        <circle className="truck-wheel" cx="10" cy="8" r="3.2" />
        <g transform="translate(0 -32)" className="pill">
          <rect x={-pillWidth / 2} y={compact ? -18 : -13} width={pillWidth} height={compact ? 34 : 25} rx={compact ? 17 : 12.5} />
          <text textAnchor="middle" y={compact ? 7 : 4.5}>
            {temperature.toFixed(1)} °C
          </text>
        </g>
      </g>

      {activeTool && <ToolChip tool={activeTool} x={here.x} y={here.y} compact={compact} />}
    </svg>
  );
}
