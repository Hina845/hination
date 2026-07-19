"use client";

import { Megaphone, PaperPlaneTilt, Sparkle, X } from "@phosphor-icons/react";
import { useActionState, useCallback, useEffect, useMemo, useRef, useState } from "react";

import RangeSlider from "@/components/RangeSlider";
import { sendSms, type SmsFormState } from "@/app/manage/actions";
import type { ForecastArea } from "@/types/forecast";

const emptySmsState: SmsFormState = {};

// Combined display level for an area — mirrors ForecastMap.displayLevel (overall ?? raw).
function displayLevel(area: ForecastArea): number {
  return area.danger.overallLevel ?? area.danger.level;
}

// "Send SMS to dangerous areas" panel: pick a danger-level band, review the matched areas
// and recipients, edit the auto-generated message, and blast. Kept as its own component so
// its useActionState resets every time the dropdown is (re)opened — the parent remounts it
// with a fresh key. Sending is the shared `sendSms` server action, scoped to the in-band
// area ids.
export default function BlastDropdown({
  dayAreas,
  citizensByArea,
  triggerRef,
  onClose,
  onSent,
}: {
  dayAreas: ForecastArea[];
  citizensByArea: Record<string, number>;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onSent: () => void;
}) {
  const [range, setRange] = useState<[number, number]>([4, 5]);
  const [message, setMessage] = useState("");
  const dirty = useRef(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const [state, action, pending] = useActionState(sendSms, emptySmsState);

  const areas = useMemo(
    () =>
      dayAreas
        .filter((area) => {
          const level = displayLevel(area);
          return level >= range[0] && level <= range[1];
        })
        .sort((a, b) => displayLevel(b) - displayLevel(a)),
    [dayAreas, range],
  );
  const areaIds = useMemo(() => areas.map((area) => area.id), [areas]);
  const recipients = useMemo(
    () => areaIds.reduce((sum, id) => sum + (citizensByArea[id] ?? 0), 0),
    [areaIds, citizensByArea],
  );

  const buildMessage = useCallback(() => {
    const names = areas.map((area) => area.name);
    const shown = names.slice(0, 4).join(", ");
    const rest = names.length > 4 ? ` và ${names.length - 4} khu vực khác` : "";
    const where = names.length > 0 ? `${shown}${rest}` : "khu vực của bạn";
    return `CẢNH BÁO THIÊN TAI: ${where} đang ở mức nguy hiểm cấp ${range[0]}–${range[1]}. Người dân chủ động di chuyển đến nơi an toàn và theo dõi thông báo tiếp theo.`;
  }, [areas, range]);

  // Keep the generated text in sync with the selection until the chief edits it.
  useEffect(() => {
    if (!dirty.current) setMessage(buildMessage());
  }, [buildMessage]);

  // Refresh the map summary counter after a successful blast.
  useEffect(() => {
    if (typeof state.sent === "number") onSent();
  }, [state.sent, onSent]);

  // Dismiss on outside click / Escape, ignoring the trigger button.
  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, triggerRef]);

  return (
    <div className="notif-dropdown blast-dropdown" ref={panelRef} role="dialog" aria-label="Gửi SMS tới khu vực nguy hiểm">
      <header className="notif-dropdown__head">
        <h2>Gửi SMS khu vực nguy hiểm</h2>
        <button type="button" className="notif-dropdown__close" aria-label="Đóng" onClick={onClose}><X /></button>
      </header>
      {typeof state.sent === "number" ? (
        <p className="blast-dropdown__success"><PaperPlaneTilt weight="fill" /> Đã gửi tới {state.sent} người dân.</p>
      ) : (
        <form action={action} className="blast-dropdown__form">
          <div className="blast-dropdown__field">
            <label>Mức độ nguy hiểm: cấp {range[0]}–{range[1]}</label>
            <RangeSlider
              min={1}
              max={5}
              value={range}
              onChange={setRange}
              ariaLabelMin="Cấp tối thiểu"
              ariaLabelMax="Cấp tối đa"
            />
          </div>
          <p className="blast-dropdown__count">
            <strong>{areas.length}</strong> khu vực · <strong>{recipients}</strong> người dân
          </p>
          <div className="blast-dropdown__field">
            <label htmlFor="blast-message">Nội dung tin nhắn</label>
            <textarea
              id="blast-message"
              name="message"
              rows={4}
              required
              value={message}
              onChange={(event) => {
                dirty.current = true;
                setMessage(event.target.value);
              }}
            />
            <button
              type="button"
              className="blast-dropdown__regen"
              onClick={() => {
                dirty.current = false;
                setMessage(buildMessage());
              }}
            >
              <Sparkle weight="fill" /> Tạo lại nội dung
            </button>
          </div>
          <input type="hidden" name="areaIds" value={JSON.stringify(areaIds)} />
          {state.error && <p className="blast-dropdown__error" role="alert">{state.error}</p>}
          <button type="submit" className="blast-dropdown__send" disabled={pending || recipients === 0}>
            <Megaphone weight="fill" /> {pending ? "Đang gửi…" : `Gửi tới ${recipients} người`}
          </button>
        </form>
      )}
    </div>
  );
}
