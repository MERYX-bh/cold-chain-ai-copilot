import { useEffect, useState } from "react";

export type Route = "journey" | "console" | "audit";
export const DEFAULT_ROUTE: Route = "journey";
const ROUTES: Route[] = ["journey", "console", "audit"];

export function parseRoute(hash: string): Route {
  const name = hash.replace(/^#\/?/, "");
  return (ROUTES as string[]).includes(name) ? (name as Route) : DEFAULT_ROUTE;
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
