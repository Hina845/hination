"use client";

import { Question } from "@phosphor-icons/react";

import { requestReplay, type TourPage } from "@/lib/onboarding";

/**
 * Small "?" button that replays the current page's onboarding tour. Placement (and base
 * styling) is up to the host via `className`; it dispatches the replay event that
 * OnboardingTour listens for.
 */
export default function TourHelpButton({ page, className }: { page: TourPage; className?: string }) {
  return (
    <button
      type="button"
      className={className}
      aria-label="Xem lại hướng dẫn"
      title="Xem lại hướng dẫn"
      onClick={() => requestReplay(page)}
    >
      <Question weight="bold" />
    </button>
  );
}
