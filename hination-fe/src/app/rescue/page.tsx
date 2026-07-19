import ManageSidebar from "@/components/ManageSidebar";
import RescueConsole, { type RescueRequestView } from "@/components/RescueConsole";
import { getSessionUser } from "@/lib/auth";
import { listActiveEmergencyContacts } from "@/lib/emergency-contacts";
import { areaOptionsFrom, getForecast } from "@/lib/forecast";
import { listRecentHelpRequests } from "@/lib/help-requests";
import { nearestArea } from "@/lib/geo";

// better-sqlite3 requires the Node.js runtime, and the SOS list + number list must always
// reflect live data, so this screen must never be statically cached.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Open to everyone (chief + rescuers + residents). A session only decides whether added
// numbers are permanent and whether delete controls appear.
export default async function RescuePage() {
  const user = await getSessionUser();

  const forecast = await getForecast();
  const areas = forecast?.days[0]?.areas ?? [];
  const areaOptions = areaOptionsFrom(forecast, {});

  // Turn each request's raw coordinates into the nearest commune name (null if the forecast
  // backend is down — the UI then shows coordinates only).
  const requests: RescueRequestView[] = listRecentHelpRequests().map(
    (request) => ({
      id: request.id,
      lat: request.lat,
      lng: request.lng,
      reason: request.reason,
      place: request.place,
      source: request.source,
      createdAt: request.createdAt,
      locationName: nearestArea({ lat: request.lat, lng: request.lng }, areas)?.name ?? null,
    }),
  );

  const contacts = listActiveEmergencyContacts();

  return (
    <div className="flex min-h-svh bg-[#eef2f6] text-[#0f172a]">
      <ManageSidebar active="rescue" />
      <RescueConsole
        requests={requests}
        contacts={contacts}
        areaOptions={areaOptions}
        isChief={!!user}
      />
    </div>
  );
}
