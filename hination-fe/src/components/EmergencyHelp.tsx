"use client";

import { ArrowClockwise, CaretDown, CheckCircle, Lifebuoy, MapPin, Phone, Warning } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { haversineKm } from "@/lib/geo";
import type { EmergencyContact } from "@/types/emergency-contact";

type Status = "idle" | "locating" | "sending" | "success" | "error";

// A contact with the caller's distance to it (km), when their location is known.
type RankedContact = EmergencyContact & { distanceKm: number | null };

// Vietnam's national emergency hotlines, always shown as a fallback so the picker is never
// empty (they have no location, so they sort after any located local responder). Negative ids
// keep them from colliding with DB rows.
const NATIONAL_HOTLINES: RankedContact[] = [
  { id: -112, name: "Cứu nạn, cứu hộ (112)", phone: "112", areaId: null, areaName: "Toàn quốc", lat: null, lng: null, createdAt: 0, expiresAt: null, distanceKm: null },
  { id: -115, name: "Cấp cứu y tế (115)", phone: "115", areaId: null, areaName: "Toàn quốc", lat: null, lng: null, createdAt: 0, expiresAt: null, distanceKm: null },
  { id: -114, name: "Cứu hỏa (114)", phone: "114", areaId: null, areaName: "Toàn quốc", lat: null, lng: null, createdAt: 0, expiresAt: null, distanceKm: null },
  { id: -113, name: "Công an (113)", phone: "113", areaId: null, areaName: "Toàn quốc", lat: null, lng: null, createdAt: 0, expiresAt: null, distanceKm: null },
];

// "0912… · Xã B · 2.3 km" — the trailing parts appear only when known.
function contactMeta(contact: RankedContact): string {
  return [
    contact.phone,
    contact.areaName ?? undefined,
    contact.distanceKm !== null ? `${contact.distanceKm.toFixed(1)} km` : undefined,
  ]
    .filter(Boolean)
    .join(" · ");
}

// Resolve the browser's current position, or null if unavailable/denied/timed out. Never
// rejects — a denied prompt just means the server falls back to IP geolocation.
function getPosition(): Promise<{ lat: number; lng: number } | null> {
  if (typeof navigator === "undefined" || !navigator.geolocation) return Promise.resolve(null);
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );
  });
}

/**
 * Citizen SOS screen. Replaces the map on phones (and is reachable via the FAB on desktop).
 * A single big button captures location (browser GPS, IP fallback on the server) plus an
 * optional reason and posts an anonymous help request. See src/app/api/help-requests.
 */
export default function EmergencyHelp() {
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [gpsUsed, setGpsUsed] = useState(false);
  const [contacts, setContacts] = useState<RankedContact[]>(NATIONAL_HOTLINES);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showOthers, setShowOthers] = useState(false);
  const busy = status === "locating" || status === "sending";

  // The picker's current number: the one the citizen tapped, else the nearest (first) contact.
  const selected = contacts.find((contact) => contact.id === selectedId) ?? contacts[0] ?? null;

  // Load local emergency numbers once and sort them nearest-first using the caller's location,
  // then append the national hotlines (which have no location, so they land at the end). The
  // list always keeps at least the hotlines, so the picker is never empty even if the fetch
  // fails or no local numbers have been added yet.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [response, position] = await Promise.all([fetch("/api/emergency-contacts"), getPosition()]);
        if (!active || !response.ok) return;
        const data = (await response.json()) as { contacts: EmergencyContact[] };
        const ranked: RankedContact[] = data.contacts.map((contact) => ({
          ...contact,
          distanceKm:
            position && contact.lat !== null && contact.lng !== null
              ? haversineKm(position, { lat: contact.lat, lng: contact.lng })
              : null,
        }));
        ranked.sort((a, b) => {
          if (a.distanceKm === null) return b.distanceKm === null ? 0 : 1;
          if (b.distanceKm === null) return -1;
          return a.distanceKm - b.distanceKm;
        });
        if (active) setContacts([...ranked, ...NATIONAL_HOTLINES]);
      } catch {
        // ignore — the hotlines remain in state, so calling still works
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function submit() {
    setStatus("locating");
    const position = await getPosition();
    setGpsUsed(position !== null);
    setStatus("sending");
    try {
      const response = await fetch("/api/help-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...(position ?? {}), reason: reason.trim() || undefined }),
      });
      if (!response.ok) throw new Error("request failed");
      setStatus("success");
    } catch {
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <section className="emergency-screen emergency-screen--done" aria-live="polite">
        <CheckCircle weight="fill" className="emergency-icon emergency-icon--ok" />
        <h1>Đã gửi yêu cầu cứu trợ</h1>
        <p className="emergency-lead">
          {gpsUsed
            ? "Đội cứu hộ đã nhận được vị trí chính xác của bạn. Hãy giữ an toàn và chờ hỗ trợ."
            : "Đội cứu hộ đã nhận được yêu cầu và vị trí gần đúng của bạn. Hãy giữ an toàn và chờ hỗ trợ."}
        </p>
        <button
          type="button"
          className="emergency-secondary"
          onClick={() => {
            setReason("");
            setStatus("idle");
          }}
        >
          Gửi yêu cầu khác
        </button>
      </section>
    );
  }

  return (
    <section className="emergency-screen" aria-label="Yêu cầu trợ giúp khẩn cấp">
      <Lifebuoy weight="fill" className="emergency-icon" />
      <h1>Bạn đang cần trợ giúp?</h1>
      <p className="emergency-lead">
        Nhấn nút bên dưới để gửi tín hiệu cầu cứu kèm vị trí của bạn tới trưởng bản và đội cứu hộ.
      </p>

      <label className="emergency-field">
        <span>Mô tả tình huống (không bắt buộc)</span>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          maxLength={300}
          rows={3}
          placeholder="Ví dụ: nhà bị ngập, có người mắc kẹt…"
          disabled={busy}
        />
      </label>

      <button type="button" className="emergency-action" onClick={submit} disabled={busy}>
        {busy ? (
          <>
            <ArrowClockwise weight="bold" className="spin" />
            {status === "locating" ? "Đang lấy vị trí…" : "Đang gửi…"}
          </>
        ) : (
          <>
            <Lifebuoy weight="fill" />
            Tôi đang cần trợ giúp
          </>
        )}
      </button>

      <p className="emergency-hint">
        <MapPin weight="fill" /> Vui lòng cho phép truy cập vị trí để đội cứu hộ tìm bạn nhanh hơn.
      </p>

      {selected && (
        <div className="emergency-contacts">
          <span className="emergency-contacts-title">Gọi cứu hộ khẩn cấp</span>
          <div className="emergency-picker">
            <a href={`tel:${selected.phone}`} className="emergency-call emergency-call--primary">
              <Phone weight="fill" />
              <span className="emergency-call-body">
                <span className="emergency-call-name">Gọi {selected.name}</span>
                <span className="emergency-call-meta">{contactMeta(selected)}</span>
              </span>
            </a>

            {contacts.length > 1 && (
              <div className="emergency-others">
                <button
                  type="button"
                  className="emergency-others-toggle"
                  onClick={() => setShowOthers((open) => !open)}
                  aria-expanded={showOthers}
                >
                  <CaretDown weight="bold" /> Số điện thoại khác ({contacts.length - 1})
                </button>
                {showOthers && (
                  <ul className="emergency-others-menu">
                    {contacts.map((contact) => (
                      <li key={contact.id}>
                        <button
                          type="button"
                          className="emergency-others-item"
                          aria-current={contact.id === selected.id ? "true" : undefined}
                          onClick={() => {
                            setSelectedId(contact.id);
                            setShowOthers(false);
                          }}
                        >
                          <span className="emergency-call-name">{contact.name}</span>
                          <span className="emergency-call-meta">{contactMeta(contact)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {status === "error" && (
        <p className="emergency-error" role="alert">
          <Warning weight="fill" /> Không thể gửi yêu cầu. Vui lòng kiểm tra kết nối và thử lại.
        </p>
      )}
    </section>
  );
}
