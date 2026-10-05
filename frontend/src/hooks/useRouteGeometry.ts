import { useCallback, useState } from "react";
import { approximateFractions, routeFor, type Scenario } from "../lib/route";

/** Station positions along the drawn route: estimated first, then replaced by the measured ones. */
export function useRouteGeometry(scenario: Scenario) {
  const [measured, setMeasured] = useState<{ scenario: Scenario; fractions: number[] } | null>(null);
  const fractions = measured?.scenario === scenario ? measured.fractions : approximateFractions(routeFor(scenario));
  const report = useCallback((next: number[]) => setMeasured({ scenario, fractions: next }), [scenario]);
  return { fractions, report };
}
