"use client";

import { useEffect, useState } from "react";

// Matches the `@media (max-width: 520px)` mobile breakpoint used throughout globals.css.
const MOBILE_QUERY = "(max-width: 520px)";

/**
 * True on small (phone) viewports. SSR-safe: starts `false` on the server and first client
 * render, then syncs to the real match in an effect (avoids a hydration mismatch). Used to
 * default the app to the citizen SOS screen on phones and the map on desktop.
 */
export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const query = window.matchMedia(MOBILE_QUERY);
    const update = () => setIsMobile(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return isMobile;
}
