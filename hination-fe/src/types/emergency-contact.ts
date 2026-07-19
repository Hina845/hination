// Emergency phone number a chief or visitor adds on /rescue, surfaced to citizens on the
// SOS screen (/app) as one-tap `tel:` buttons. Pure type — no server imports — so it can
// cross into client components (EmergencyHelp, RescueConsole) without dragging in sqlite.

export type EmergencyContact = {
  id: number;
  name: string;
  phone: string;
  areaId: string | null; // forecast/commune id the number serves
  areaName: string | null; // denormalized commune name for display
  lat: number | null; // commune centroid, for nearest-first sorting on the citizen screen
  lng: number | null;
  createdAt: number; // epoch ms
  // null = never expires (added by a logged-in chief). A timestamp = added anonymously and
  // aged off 48h after creation (see listActiveEmergencyContacts).
  expiresAt: number | null;
};
