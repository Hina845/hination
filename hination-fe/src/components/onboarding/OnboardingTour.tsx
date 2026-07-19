"use client";

import { driver, type Driver, type DriveStep } from "driver.js";
import "driver.js/dist/driver.css";
import { useEffect, useRef } from "react";

import { hasSeenTour, markTourSeen, REPLAY_TOUR_EVENT, type TourPage } from "@/lib/onboarding";

import { TOUR_STEPS } from "./tours";

// The tour is desktop-only. 768px matches the `md:` breakpoint where the sidebar appears, so
// every anchored control the tour points at is actually on screen.
const DESKTOP_QUERY = "(min-width: 768px)";

/**
 * Headless controller for a page's first-run guided tour. Renders nothing.
 *
 * On mount (desktop only, once per page) it auto-starts the driver.js spotlight tour and marks
 * the page seen when finished/closed. It also listens for the `hination:replay-tour` event so
 * the page's "?" button can restart the tour on demand. Steps whose target element is missing
 * (e.g. chief-only controls for anonymous viewers) are filtered out before driving.
 */
export default function OnboardingTour({ page }: { page: TourPage }) {
  // Keep a single live driver so an in-progress tour is torn down before a replay starts.
  const driverRef = useRef<Driver | null>(null);

  useEffect(() => {
    const isDesktop = () => window.matchMedia(DESKTOP_QUERY).matches;
    const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const start = () => {
      if (!isDesktop()) return;

      // Only keep steps whose anchor exists in the DOM (or that are element-less welcome cards).
      const steps: DriveStep[] = TOUR_STEPS[page].filter(
        (step) => !step.element || document.querySelector(step.element as string),
      );
      if (steps.length === 0) return;

      driverRef.current?.destroy();
      const driverObj = driver({
        steps,
        showProgress: true,
        progressText: "Bước {{current}}/{{total}}",
        nextBtnText: "Tiếp",
        prevBtnText: "Quay lại",
        doneBtnText: "Xong",
        showButtons: ["next", "previous", "close"],
        popoverClass: "hination-tour",
        allowClose: true,
        animate: !prefersReducedMotion(),
        onDestroyed: () => {
          markTourSeen(page);
          driverRef.current = null;
        },
      });
      driverRef.current = driverObj;
      driverObj.drive();
    };

    // Auto-start on first desktop visit. rAF + a short delay lets the client body (map panels,
    // tables, sidebar) paint so the anchors resolve.
    let raf = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    if (!hasSeenTour(page) && isDesktop()) {
      raf = requestAnimationFrame(() => {
        timer = setTimeout(start, 400);
      });
    }

    // Replay button path: restart regardless of the seen flag, but only for this page.
    const onReplay = (event: Event) => {
      if ((event as CustomEvent<{ page: TourPage }>).detail?.page === page) start();
    };
    window.addEventListener(REPLAY_TOUR_EVENT, onReplay);

    return () => {
      cancelAnimationFrame(raf);
      if (timer) clearTimeout(timer);
      window.removeEventListener(REPLAY_TOUR_EVENT, onReplay);
      driverRef.current?.destroy();
      driverRef.current = null;
    };
  }, [page]);

  return null;
}
