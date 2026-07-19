// First-run onboarding tour persistence. Each main screen shows a short guided tour the first
// time a (desktop) visitor opens it; we remember that per page in localStorage so it never
// repeats. This is the app's only localStorage usage — every access is guarded so a disabled
// or private-mode store can never crash the page.

// Bump when the tour steps change meaningfully so returning users see the refreshed tour once.
export const TOUR_VERSION = 1;

export type TourPage = "map" | "manage" | "radio" | "rescue";

const keyFor = (page: TourPage) => `hination.tour.${page}`;

export function hasSeenTour(page: TourPage): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(keyFor(page)) === String(TOUR_VERSION);
  } catch {
    return false;
  }
}

export function markTourSeen(page: TourPage): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(keyFor(page), String(TOUR_VERSION));
  } catch {
    // Storage unavailable (private mode / quota). The tour simply shows again next visit.
  }
}

export function clearTour(page: TourPage): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(keyFor(page));
  } catch {
    // No-op — nothing to clear if storage is unavailable.
  }
}

// Fired by the "?" replay button on each page; OnboardingTour listens and restarts the matching
// page's tour regardless of the seen flag.
export const REPLAY_TOUR_EVENT = "hination:replay-tour";

export function requestReplay(page: TourPage): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(REPLAY_TOUR_EVENT, { detail: { page } }));
}
