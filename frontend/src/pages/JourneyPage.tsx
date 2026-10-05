import { useEffect, useState } from "react";
import { RouteMap } from "../components/RouteMap";
import { TemperatureChart } from "../components/TemperatureChart";
import { prefersReducedMotion, useAnimatedProgress } from "../hooks/useAnimatedProgress";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useRouteGeometry } from "../hooks/useRouteGeometry";
import {
  TEMP_LIMIT_C,
  agentPlan,
  revealedSteps,
  routeFor,
  segmentAt,
  segmentInfo,
  temperatureAt,
  temperatureStatus,
  type Scenario,
} from "../lib/route";
import { toolInfo } from "../lib/toolInfo";

const SCENARIOS: { id: Scenario; label: string; summary: string }[] = [
  { id: "normal", label: "Normal journey", summary: "Everything stays inside the limits, so the agent has nothing to do." },
  { id: "breach", label: "Temperature breach", summary: "The cooling unit fails on the road to the port and the cargo warms up." },
  { id: "congestion", label: "Port congestion", summary: "The port is jammed: the SOP says to divert the shipment to San Bernardino." },
];

const STATUS_TEXT = {
  ok: "Inside the 0 to 4 °C limit",
  warning: "Close to the 4 °C limit",
  breach: "Breach: outside the SOP limit",
} as const;

export function JourneyPage() {
  const [scenario, setScenario] = useState<Scenario>("breach");
  const [playing, setPlaying] = useState(!prefersReducedMotion());
  const [speed, setSpeed] = useState(1);
  const [progress, setProgress] = useAnimatedProgress({ playing, speed, durationSeconds: 24, loop: false });
  const { fractions, report } = useRouteGeometry(scenario);
  const narrow = useMediaQuery("(max-width: 640px)");

  useEffect(() => {
    if (playing && progress >= 1) setPlaying(false);
  }, [playing, progress]);

  const points = routeFor(scenario);
  const segment = segmentAt(progress, fractions);
  const info = segmentInfo(points[segment].id, points[Math.min(segment + 1, points.length - 1)].id);
  const temperature = temperatureAt(progress, scenario, fractions);
  const status = temperatureStatus(temperature);
  const plan = agentPlan(scenario);
  const revealed = revealedSteps(progress, scenario, fractions);
  const activeTool = revealed > 0 ? plan[revealed - 1].tool : null;
  const finished = progress >= 1;

  const choose = (next: Scenario) => {
    setScenario(next);
    setProgress(0);
    setPlaying(true);
  };

  const togglePlay = () => {
    if (finished) setProgress(0);
    setPlaying(finished ? true : !playing);
  };

  return (
    <div className="journey">
      <header className="page-head">
        <h1>Follow a shipment through the cold chain</h1>
        <p className="muted">
          A refrigerated truck leaves the packing house and must stay between 0 and {TEMP_LIMIT_C.toFixed(1)} °C all the way to the store. Pick a scenario and watch where
          the agent steps in. This is an illustration, not live data.
        </p>
      </header>

      <div className="tabs" role="tablist" aria-label="Scenario">
        {SCENARIOS.map((item) => (
          <button key={item.id} role="tab" type="button" aria-selected={scenario === item.id} className={scenario === item.id ? "tab tab--on" : "tab"} onClick={() => choose(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      <p className="scenario-summary">{SCENARIOS.find((item) => item.id === scenario)?.summary}</p>

      <div className="card map-card">
        <RouteMap scenario={scenario} progress={progress} activeTool={activeTool} onFractions={report} compact={narrow} />

        <div className="controls">
          <button type="button" className="button button--primary" onClick={togglePlay}>
            {finished ? "Replay" : playing ? "Pause" : "Play"}
          </button>
          <label className="control">
            <span>Journey</span>
            <input
              type="range"
              min={0}
              max={1000}
              value={Math.round(progress * 1000)}
              onChange={(event) => {
                setPlaying(false);
                setProgress(Number(event.target.value) / 1000);
              }}
              aria-label="Position along the journey"
            />
          </label>
          <label className="control control--speed">
            <span>Speed</span>
            <select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>
              <option value={0.5}>0.5x</option>
              <option value={1}>1x</option>
              <option value={2}>2x</option>
            </select>
          </label>
        </div>

        <TemperatureChart scenario={scenario} fractions={fractions} progress={progress} />
      </div>

      <div className="two">
        <section className="card" aria-live="polite">
          <h2>Where we are</h2>
          <p className={`reading reading--${status}`}>
            <strong>{temperature.toFixed(1)} °C</strong> {STATUS_TEXT[status]}
          </p>
          <h3>{info.title}</h3>
          <p>{info.text}</p>
          <p className="muted small">Tools watching this leg</p>
          <div className="chips">
            {info.tools.map((tool) => (
              <span key={tool} className="chip-tag">
                {toolInfo(tool).label}
              </span>
            ))}
          </div>
        </section>

        <section className="card" aria-live="polite">
          <h2>What the agent does</h2>
          {plan.length === 0 ? (
            <p className="muted">Nothing to report: every reading stays inside the limits, so the agent stays idle.</p>
          ) : revealed === 0 ? (
            <p className="muted">Watching the readings. It reacts as soon as something leaves the limits.</p>
          ) : (
            <ol className="steps">
              {plan.slice(0, revealed).map((step, index) => (
                <li key={`${scenario}-${index}`} className={`step ${step.tool === null ? "step--human" : ""}`}>
                  <span className="step-n">{index + 1}</span>
                  <div>
                    <strong>{step.title}</strong>
                    {step.tool && <span className="chip-tag">{toolInfo(step.tool).label}</span>}
                    <p>{step.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
          {plan.length > 0 && <p className="muted small">The approval step is simulated here. In the console you approve it yourself.</p>}
        </section>
      </div>
    </div>
  );
}
