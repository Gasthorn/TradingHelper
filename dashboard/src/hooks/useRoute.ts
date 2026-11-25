/** Route courante, suivie via `hashchange` (spec F09 — R1). */
import { useEffect, useState } from "preact/hooks";

import { type Route, parseHash } from "../lib/routes";

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash));
    };
    window.addEventListener("hashchange", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
    };
  }, []);
  return route;
}
