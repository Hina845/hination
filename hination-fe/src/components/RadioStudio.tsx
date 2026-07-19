"use client";

import {
  Broadcast,
  CaretDown,
  ChatCircleDots,
  CheckCircle,
  Clock,
  DeviceMobile,
  MapTrifold,
  Megaphone,
  Microphone,
  Pause,
  PencilSimple,
  Play,
  Sparkle,
  Trash,
  Warning,
  WarningOctagon,
  X,
} from "@phosphor-icons/react";
import Link from "next/link";
import { startTransition, useActionState, useCallback, useEffect, useMemo, useRef, useState } from "react";

import VoiceRecorderModal from "@/components/VoiceRecorderModal";
import WaveBars from "@/components/WaveBars";
import {
  removeBroadcast,
  removeRecording,
  renameRecordingAction,
  submitBroadcast,
  type BroadcastFormState,
} from "@/app/radio/actions";
import type { AreaOption } from "@/types/area";
import type { Broadcast as BroadcastRecord, BroadcastChannel, BroadcastVoice } from "@/types/broadcast";
import type { DisasterType } from "@/types/forecast";
import type { VoiceRecording } from "@/types/recording";

// Alert summary derived server-side from the forecast (see app/radio/page.tsx). Drives the
// red alert card + the AI risk-summary bullets.
export type RadioAlert = {
  disasterLabel: string;
  communeName: string;
  areaNames: string[];
  level: number;
  tierLabel: string;
  tierColor: string;
  rainfallMm: number;
  windGustKmh: number;
  peakWindow: string;
  dominantDisaster: DisasterType;
  riskMessage: string;
  riskAreaIds: string[];
};

const MESSAGE_LIMIT = 280;
const emptyBroadcastState: BroadcastFormState = {};

const REPEAT_OPTIONS = [
  { label: "Phát 1 lần", repeat: 1, gap: 0 },
  { label: "2 lần · cách nhau 5 phút", repeat: 2, gap: 5 },
  { label: "3 lần · cách nhau 5 phút", repeat: 3, gap: 5 },
  { label: "3 lần · cách nhau 10 phút", repeat: 3, gap: 10 },
] as const;

const CHANNELS: BroadcastChannel[] = ["loudspeaker", "sms", "zalo"];

// Per-disaster action guidance woven into the auto-generated broadcast. Keeps the spoken
// instruction specific to what people should actually do for that hazard.
const GUIDANCE: Record<DisasterType, { full: string; short: string }> = {
  flood: {
    full: "Người dân không đi qua suối, ngầm tràn. Các hộ ven suối chuẩn bị giấy tờ, thuốc men và sẵn sàng di chuyển đến nhà văn hóa bản khi có hiệu lệnh.",
    short: "không qua suối, ngầm tràn",
  },
  storm: {
    full: "Người dân chằng chống nhà cửa, không ra ngoài khi mưa lớn. Chuẩn bị đèn pin, nước uống và sẵn sàng di chuyển khi có hiệu lệnh.",
    short: "ở trong nhà an toàn",
  },
  landslide: {
    full: "Người dân tránh xa taluy, sườn dốc. Các hộ dưới chân đồi chủ động di dời đến nơi an toàn khi có hiệu lệnh.",
    short: "tránh xa sườn dốc, taluy",
  },
  wind: {
    full: "Người dân gia cố mái nhà, tránh trú dưới cây lớn và cột điện. Sẵn sàng di chuyển khi có hiệu lệnh.",
    short: "tránh cây lớn, cột điện",
  },
  wildfire: {
    full: "Người dân không đốt nương, dọn vật liệu dễ cháy quanh nhà và sẵn sàng sơ tán khi có hiệu lệnh.",
    short: "không đốt nương",
  },
};

function guidanceFor(disaster: DisasterType) {
  return GUIDANCE[disaster] ?? GUIDANCE.flood;
}

function joinAreaNames(names: string[], max: number): string {
  if (names.length === 0) return "khu vực của bạn";
  const shown = names.slice(0, max).join(", ");
  const rest = names.length > max ? ` và ${names.length - max} nơi khác` : "";
  return `${shown}${rest}`;
}

function buildMessage(alert: RadioAlert, names: string[]): string {
  const guide = guidanceFor(alert.dominantDisaster);
  return `CẢNH BÁO ${alert.disasterLabel.toUpperCase()} MỨC ${alert.tierLabel.toUpperCase()}. Từ ${alert.peakWindow} hôm nay tại ${joinAreaNames(names, 3)}, mưa lớn còn tiếp diễn. ${guide.full}`;
}

function buildShortMessage(alert: RadioAlert, names: string[]): string {
  const guide = guidanceFor(alert.dominantDisaster);
  return `CẢNH BÁO ${alert.disasterLabel.toUpperCase()}. ${joinAreaNames(names, 2)} nguy cơ ${alert.tierLabel.toLowerCase()} từ ${alert.peakWindow}. Bà con ${guide.short}, chờ hiệu lệnh di chuyển đến nơi an toàn.`;
}

// Voice <-> option-value coding for the native <select>.
function voiceToValue(voice: BroadcastVoice): string {
  return voice.kind === "recording" ? `rec:${voice.recordingId}` : `tts:${voice.id}`;
}
function valueToVoice(value: string): BroadcastVoice {
  if (value.startsWith("rec:")) return { kind: "recording", recordingId: Number(value.slice(4)) };
  if (value === "tts:hmong") return { kind: "tts", id: "hmong" };
  return { kind: "tts", id: "kinh" };
}

// Preview source for a voice: a real audio URL for recordings / the H'Mông sample, or null
// for the Kinh TTS voice (which is spoken live via the Web Speech API).
function audioUrlForVoice(voice: BroadcastVoice): string | null {
  if (voice.kind === "recording") return `/api/recordings/${voice.recordingId}`;
  if (voice.id === "hmong") return "/hmong-speech.mp3";
  return null;
}

function formatClock(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function formatDateTime(ms: number): string {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(ms));
}

export default function RadioStudio({
  alert,
  areaOptions,
  recordings: initialRecordings,
  broadcasts,
}: {
  alert: RadioAlert | null;
  areaOptions: AreaOption[];
  recordings: VoiceRecording[];
  broadcasts: BroadcastRecord[];
}) {
  const areaById = useMemo(() => new Map(areaOptions.map((area) => [area.id, area])), [areaOptions]);

  // Local recording list, seeded from the server. A newly captured clip is added
  // optimistically (instant select) and server revalidation later re-supplies the prop;
  // resync it during render (the endorsed "adjust state when a prop changes" pattern)
  // rather than in an effect so deletions from the server are reflected too.
  const [recordings, setRecordings] = useState(initialRecordings);
  const [seenRecordings, setSeenRecordings] = useState(initialRecordings);
  if (seenRecordings !== initialRecordings) {
    setSeenRecordings(initialRecordings);
    setRecordings(initialRecordings);
  }

  // Default the targeted areas to the alert's risk band, else the highest-danger area.
  const [selectedAreaIds, setSelectedAreaIds] = useState<string[]>(() => {
    if (alert && alert.riskAreaIds.length > 0) return alert.riskAreaIds;
    return areaOptions[0] ? [areaOptions[0].id] : [];
  });

  const selectedNames = useMemo(
    () => selectedAreaIds.map((id) => areaById.get(id)?.name ?? id),
    [selectedAreaIds, areaById],
  );

  const [message, setMessage] = useState(() => (alert ? buildMessage(alert, selectedNames) : ""));
  const messageDirty = useRef(false);

  // Keep the generated text in sync with the area selection until the chief edits it.
  useEffect(() => {
    if (!messageDirty.current && alert) setMessage(buildMessage(alert, selectedNames));
  }, [alert, selectedNames]);

  const [voice, setVoice] = useState<BroadcastVoice>({ kind: "tts", id: "kinh" });
  const [channels, setChannels] = useState<Set<BroadcastChannel>>(new Set(CHANNELS));
  const [timing, setTiming] = useState<"now" | "schedule">("now");
  const [scheduledAt, setScheduledAt] = useState("");
  const [repeatIndex, setRepeatIndex] = useState(1);
  const [recorderOpen, setRecorderOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  const [state, dispatch, pending] = useActionState(submitBroadcast, emptyBroadcastState);

  // Drop a selected voice recording if it was deleted from under us (corrected during
  // render — the guard clears once voice falls back to Kinh, so it can't loop).
  if (voice.kind === "recording" && !recordings.some((rec) => rec.id === voice.recordingId)) {
    setVoice({ kind: "tts", id: "kinh" });
  }

  const unselectedAreas = useMemo(
    () => areaOptions.filter((area) => !selectedAreaIds.includes(area.id)),
    [areaOptions, selectedAreaIds],
  );

  const addArea = (id: string) => setSelectedAreaIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
  const removeArea = (id: string) => setSelectedAreaIds((prev) => prev.filter((value) => value !== id));

  // Reach figures. SMS recipients come from the real tagged-villager counts; loudspeaker
  // clusters are one per targeted bản; Zalo is a plausible follower share of the reach.
  const recipients = useMemo(
    () => selectedAreaIds.reduce((sum, id) => sum + (areaById.get(id)?.count ?? 0), 0),
    [selectedAreaIds, areaById],
  );
  const priorityHouseholds = useMemo(
    () =>
      selectedAreaIds.reduce(
        (sum, id) => sum + ((areaById.get(id)?.level ?? 0) >= 5 ? areaById.get(id)?.count ?? 0 : 0),
        0,
      ),
    [selectedAreaIds, areaById],
  );
  const clusters = Math.max(1, selectedAreaIds.length);
  const zaloFollowers = Math.round(recipients * 0.83);
  const anyChannel = channels.size > 0;
  const households = anyChannel ? recipients : 0;

  const toggleChannel = (channel: BroadcastChannel) =>
    setChannels((prev) => {
      const next = new Set(prev);
      if (next.has(channel)) next.delete(channel);
      else next.add(channel);
      return next;
    });

  const repeat = REPEAT_OPTIONS[repeatIndex];

  const buildForm = useCallback(
    (intent: "draft" | "send") => {
      const form = new FormData();
      form.append("intent", intent);
      form.append("message", message.trim());
      form.append("areaIds", JSON.stringify(selectedAreaIds));
      form.append("channels", JSON.stringify(Array.from(channels)));
      form.append("voice", JSON.stringify(voice));
      form.append("repeat", String(repeat.repeat));
      form.append("repeatGapMinutes", String(repeat.gap));
      const scheduledMs = timing === "schedule" && scheduledAt ? new Date(scheduledAt).getTime() : 0;
      form.append("scheduledAt", String(Number.isFinite(scheduledMs) ? scheduledMs : 0));
      return form;
    },
    [message, selectedAreaIds, channels, voice, repeat, timing, scheduledAt],
  );

  // dispatch() is called from onClick handlers (not a form `action` prop), so it must run
  // inside a transition or React warns and `pending` won't track correctly.
  const saveDraft = () => startTransition(() => dispatch(buildForm("draft")));
  const sendNow = () => startTransition(() => dispatch(buildForm("send")));

  // Close the preview dialog once a send succeeds. Detected by watching the action status
  // change across renders (no effect needed) so a fresh send later still reopens cleanly.
  const [seenStatus, setSeenStatus] = useState(state.status);
  if (state.status !== seenStatus) {
    setSeenStatus(state.status);
    if (state.status === "sent" || state.status === "scheduled") setPreviewOpen(false);
  }

  const voiceLabel =
    voice.kind === "recording"
      ? recordings.find((rec) => rec.id === voice.recordingId)?.name ?? "Giọng đã lưu"
      : voice.id === "hmong"
        ? "Giọng H'Mông (AI đọc)"
        : "Giọng Kinh (AI đọc)";

  if (!alert) {
    return (
      <main className="flex-1 px-6 py-10 md:px-12">
        <h1 className="text-3xl font-bold text-[#0f172a]">Đài phát thanh</h1>
        <div className="mt-8 grid place-items-center rounded-2xl border border-dashed border-[#cbd5e1] bg-white px-6 py-20 text-center">
          <Broadcast size={48} weight="thin" className="text-[#cbd5e1]" />
          <p className="mt-4 max-w-md text-lg text-[#475569]">
            Chưa tải được dữ liệu dự báo nên chưa thể soạn cảnh báo. Vui lòng thử lại khi dịch vụ dự báo hoạt động.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 px-4 py-8 md:px-10 md:py-9">
      <header className="mb-7">
        <h1 className="text-3xl font-bold text-[#0f172a]">Đài phát thanh</h1>
        <p className="mt-2 text-lg text-[#475569]">
          Soạn và phát cảnh báo hành động đến đúng bản, đúng thời điểm.
        </p>
      </header>

      {/* Success banner after a save / send. */}
      {state.status && (
        <div
          className="mb-6 flex items-center gap-3 rounded-xl border border-[#bbf7d0] bg-[#f0fdf4] px-5 py-3.5 text-[#15803d]"
          role="status"
          aria-live="polite"
        >
          <CheckCircle weight="fill" size={22} className="shrink-0" />
          <p className="text-base font-semibold">
            {state.status === "draft" && "Đã lưu bản nháp cảnh báo."}
            {state.status === "sent" &&
              `Đã phát cảnh báo qua ${state.channelCount} kênh · tiếp cận ${state.recipientCount} hộ dân.`}
            {state.status === "scheduled" &&
              `Đã hẹn giờ phát cảnh báo tới ${state.recipientCount} hộ dân.`}
          </p>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1fr)]">
        {/* ───────────────────────── LEFT COLUMN ───────────────────────── */}
        <div className="flex flex-col gap-5">
          <AlertCard alert={alert} />
          <RiskSummaryCard alert={alert} />
          <ChannelCard
            channels={channels}
            onToggle={toggleChannel}
            clusters={clusters}
            recipients={recipients}
            zaloFollowers={zaloFollowers}
            households={households}
            priorityHouseholds={priorityHouseholds}
          />
        </div>

        {/* ───────────────────────── RIGHT COLUMN ──────────────────────── */}
        <section className="rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white p-6 shadow-[0_0.75rem_2.25rem_rgb(15_23_42_/_6%)] md:p-7">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-xl font-bold text-[#0f172a]">Soạn nội dung cảnh báo</h2>
            <button
              type="button"
              onClick={() => {
                messageDirty.current = false;
                setMessage(buildMessage(alert, selectedNames));
              }}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#4f46e5] transition-colors hover:text-[#4338ca]"
            >
              <Sparkle weight="fill" size={16} /> AI gợi ý
            </button>
          </div>

          {/* Target areas */}
          <div className="mb-5">
            <label className="mb-2 block text-sm font-semibold text-[#475569]">Khu vực nhận tin</label>
            <div className="flex flex-wrap items-center gap-2 rounded-[10px] border border-[#cbd5e1] bg-white p-2.5">
              {selectedAreaIds.length === 0 && (
                <span className="px-1 text-sm text-[#94a3b8]">Chưa chọn khu vực nào</span>
              )}
              {selectedAreaIds.map((id) => (
                <span
                  key={id}
                  className="inline-flex items-center gap-1.5 rounded-full bg-[#eef2ff] py-1 pr-1.5 pl-3 text-sm font-medium text-[#4338ca]"
                >
                  {areaById.get(id)?.name ?? id}
                  <button
                    type="button"
                    onClick={() => removeArea(id)}
                    aria-label={`Bỏ ${areaById.get(id)?.name ?? id}`}
                    className="grid size-5 place-items-center rounded-full text-[#6366f1] transition-colors hover:bg-[#c7d2fe] hover:text-[#4338ca]"
                  >
                    <X size={13} weight="bold" />
                  </button>
                </span>
              ))}
              {unselectedAreas.length > 0 && (
                <select
                  value=""
                  onChange={(event) => event.target.value && addArea(event.target.value)}
                  aria-label="Thêm khu vực nhận tin"
                  className="ml-auto h-8 rounded-md border border-[#e2e8f0] bg-[#f8fafc] px-2 text-sm text-[#475569] outline-none focus:border-[#6366f1]"
                >
                  <option value="">＋ Thêm khu vực…</option>
                  {unselectedAreas.map((area) => (
                    <option key={area.id} value={area.id}>
                      {area.name} · {area.count} hộ
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {/* Message */}
          <div className="mb-5">
            <label htmlFor="broadcast-message" className="mb-2 block text-sm font-semibold text-[#475569]">
              Nội dung phát
            </label>
            <textarea
              id="broadcast-message"
              value={message}
              maxLength={MESSAGE_LIMIT}
              onChange={(event) => {
                messageDirty.current = true;
                setMessage(event.target.value);
              }}
              rows={5}
              className="w-full resize-none rounded-[10px] border border-[#cbd5e1] bg-white px-4 py-3 text-base leading-relaxed text-[#1e293b] outline-none transition-[border-color,box-shadow] duration-150 focus:border-[#6366f1] focus:shadow-[0_0_0_3px_rgb(99_102_241_/_15%)]"
            />
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  messageDirty.current = true;
                  setMessage(buildShortMessage(alert, selectedNames));
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#c7d2fe] bg-[#eef2ff] px-3 py-1.5 text-sm font-semibold text-[#4f46e5] transition-colors hover:bg-[#e0e7ff]"
              >
                <Sparkle weight="fill" size={14} /> Rút gọn, dễ nghe hơn
              </button>

              <VoicePicker
                voice={voice}
                recordings={recordings}
                onChange={setVoice}
                onRecord={() => setRecorderOpen(true)}
              />

              <span
                className={`ml-auto text-sm tabular-nums ${
                  message.length > MESSAGE_LIMIT - 20 ? "text-[#dc2626]" : "text-[#94a3b8]"
                }`}
              >
                {message.length} / {MESSAGE_LIMIT} ký tự
              </span>
            </div>
          </div>

          {/* Timing */}
          <div className="mb-5">
            <span className="mb-2 block text-sm font-semibold text-[#475569]">Thời điểm phát</span>
            <div className="flex flex-wrap items-center gap-5">
              <RadioPill checked={timing === "now"} onSelect={() => setTiming("now")} label="Phát ngay" />
              <RadioPill checked={timing === "schedule"} onSelect={() => setTiming("schedule")} label="Hẹn giờ" />
              {timing === "schedule" && (
                <input
                  type="datetime-local"
                  value={scheduledAt}
                  onChange={(event) => setScheduledAt(event.target.value)}
                  className="h-10 rounded-lg border border-[#cbd5e1] bg-white px-3 text-sm text-[#334155] outline-none focus:border-[#6366f1]"
                />
              )}
            </div>
          </div>

          {/* Repeat */}
          <div className="mb-5">
            <label htmlFor="broadcast-repeat" className="mb-2 block text-sm font-semibold text-[#475569]">
              Lặp lại
            </label>
            <div className="relative">
              <select
                id="broadcast-repeat"
                value={repeatIndex}
                onChange={(event) => setRepeatIndex(Number(event.target.value))}
                className="h-12 w-full appearance-none rounded-[10px] border border-[#cbd5e1] bg-white px-4 pr-10 text-base text-[#334155] outline-none focus:border-[#6366f1]"
              >
                {REPEAT_OPTIONS.map((option, index) => (
                  <option key={option.label} value={index}>
                    {option.label}
                  </option>
                ))}
              </select>
              <CaretDown
                size={16}
                weight="bold"
                className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-[#94a3b8]"
              />
            </div>
          </div>

          {/* Preview */}
          <div className="mb-6">
            <span className="mb-2 block text-sm font-semibold text-[#475569]">Nghe thử</span>
            <NghePlayer key={voiceToValue(voice)} voice={voice} voiceLabel={voiceLabel} message={message} />
          </div>

          {/* Actions */}
          {state.error && (
            <p className="mb-3 flex items-center gap-2 text-sm text-[#dc2626]" role="alert">
              <Warning weight="fill" size={16} /> {state.error}
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={saveDraft}
              disabled={pending || !message.trim()}
              className="h-12 rounded-lg border border-[#cbd5e1] bg-white px-5 text-base font-semibold text-[#0f172a] transition-colors hover:bg-[#f1f5f9] disabled:opacity-60"
            >
              Lưu bản nháp
            </button>
            <button
              type="button"
              onClick={() => setPreviewOpen(true)}
              disabled={!message.trim() || !anyChannel || selectedAreaIds.length === 0}
              className="inline-flex h-12 flex-1 items-center justify-center gap-2 rounded-lg bg-[#0f172a] px-6 text-base font-semibold text-white transition-colors hover:bg-[#1e293b] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Broadcast weight="fill" size={20} /> Xem trước &amp; kiểm tra
            </button>
          </div>
        </section>
      </div>

      {/* Saved voices + drafts management (the "save for later use" surface). */}
      <SavedVoices recordings={recordings} onRecord={() => setRecorderOpen(true)} />
      <BroadcastHistory broadcasts={broadcasts} areaById={areaById} />

      {recorderOpen && (
        <VoiceRecorderModal
          onClose={() => setRecorderOpen(false)}
          defaultName={alert ? `${alert.disasterLabel} – ${alert.communeName}` : undefined}
          onSaved={(recording) => {
            setRecordings((prev) => [recording, ...prev]);
            setVoice({ kind: "recording", recordingId: recording.id });
            setRecorderOpen(false);
          }}
        />
      )}

      {previewOpen && (
        <PreviewModal
          alert={alert}
          message={message}
          areaNames={selectedNames}
          channels={Array.from(channels)}
          voiceLabel={voiceLabel}
          voice={voice}
          repeatLabel={repeat.label}
          timing={timing}
          scheduledAt={scheduledAt}
          households={households}
          recipients={recipients}
          error={state.error}
          pending={pending}
          onConfirm={sendNow}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </main>
  );
}

/* ───────────────────────────── Left cards ───────────────────────────── */

function AlertCard({ alert }: { alert: RadioAlert }) {
  return (
    <div
      className="relative overflow-hidden rounded-2xl border p-5"
      style={{ borderColor: `${alert.tierColor}55`, backgroundColor: `${alert.tierColor}12` }}
    >
      <span
        className="inline-block rounded-md px-2 py-0.5 text-[11px] font-bold tracking-wide text-white uppercase"
        style={{ backgroundColor: alert.tierColor }}
      >
        {alert.tierLabel}
      </span>
      <WarningOctagon
        weight="fill"
        size={30}
        className="absolute top-5 right-5"
        style={{ color: alert.tierColor }}
      />
      <h3 className="mt-3 text-xl font-bold text-[#0f172a]">
        {alert.disasterLabel} · {alert.communeName}
      </h3>
      <p className="mt-1 text-sm text-[#475569]">
        {alert.areaNames.join(", ")} · {alert.peakWindow}
      </p>
    </div>
  );
}

function RiskSummaryCard({ alert }: { alert: RadioAlert }) {
  return (
    <div className="rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white p-5 shadow-[0_0.5rem_1.5rem_rgb(15_23_42_/_5%)]">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-[#0f172a]">Tóm tắt nguy cơ</h3>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-[#4f46e5]">
          <Sparkle weight="fill" size={13} /> AI PHÂN TÍCH
        </span>
      </div>
      <ul className="mt-4 flex flex-col gap-3.5">
        <RiskBullet
          color="#3b82f6"
          title={`Mưa lớn thượng nguồn`}
          detail={`${Math.max(40, alert.rainfallMm)}–${Math.max(60, alert.rainfallMm + 35)} mm trong 6 giờ tới`}
        />
        <RiskBullet
          color="#f97316"
          title="Đất đã bão hòa, mực suối tăng nhanh"
          detail="Nguy cơ cao nhất tại các hộ ven suối"
        />
      </ul>
      <div className="mt-5 flex items-center justify-between">
        <Link
          href="/app"
          className="inline-flex items-center gap-2 rounded-lg border border-[#cbd5e1] bg-white px-3.5 py-2 text-sm font-semibold text-[#0f172a] transition-colors hover:bg-[#f1f5f9]"
        >
          <MapTrifold size={17} /> Mở trên bản đồ
        </Link>
        <span className="text-xs text-[#94a3b8]">Cập nhật vừa xong</span>
      </div>
    </div>
  );
}

function RiskBullet({ color, title, detail }: { color: string; title: string; detail: string }) {
  return (
    <li className="flex gap-3">
      <span className="mt-1.5 size-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />
      <div>
        <p className="text-base font-semibold text-[#1e293b]">{title}</p>
        <p className="text-sm text-[#64748b]">{detail}</p>
      </div>
    </li>
  );
}

function ChannelCard({
  channels,
  onToggle,
  clusters,
  recipients,
  zaloFollowers,
  households,
  priorityHouseholds,
}: {
  channels: Set<BroadcastChannel>;
  onToggle: (channel: BroadcastChannel) => void;
  clusters: number;
  recipients: number;
  zaloFollowers: number;
  households: number;
  priorityHouseholds: number;
}) {
  const rows: {
    key: BroadcastChannel;
    icon: React.ReactNode;
    label: string;
    detail: string;
    dot: string;
  }[] = [
    {
      key: "loudspeaker",
      icon: <Megaphone weight="fill" size={18} className="text-[#4f46e5]" />,
      label: "Loa phát thanh bản",
      detail: `${clusters}/${clusters} cụm loa đang trực tuyến`,
      dot: "#22c55e",
    },
    {
      key: "sms",
      icon: <DeviceMobile weight="fill" size={18} className="text-[#4f46e5]" />,
      label: "SMS",
      detail: `${recipients.toLocaleString("vi-VN")} số điện thoại`,
      dot: "#3b82f6",
    },
    {
      key: "zalo",
      icon: <ChatCircleDots weight="fill" size={18} className="text-[#4f46e5]" />,
      label: "Zalo OA",
      detail: `${zaloFollowers.toLocaleString("vi-VN")} người theo dõi`,
      dot: "#3b82f6",
    },
  ];

  return (
    <div className="rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white p-5 shadow-[0_0.5rem_1.5rem_rgb(15_23_42_/_5%)]">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-[#0f172a]">Kênh phát</h3>
        <span className="text-sm font-bold text-[#16a34a]">
          {households.toLocaleString("vi-VN")} HỘ
        </span>
      </div>

      <ul className="mt-4 flex flex-col gap-1">
        {rows.map((row) => {
          const active = channels.has(row.key);
          return (
            <li key={row.key}>
              <label className="flex cursor-pointer items-center gap-3 rounded-lg px-1 py-2.5 transition-colors hover:bg-[#f8fafc]">
                <input
                  type="checkbox"
                  checked={active}
                  onChange={() => onToggle(row.key)}
                  className="size-[18px] shrink-0 accent-[#4f46e5]"
                />
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-[#eef2ff]">{row.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-base font-semibold text-[#0f172a]">{row.label}</span>
                  <span className="block text-sm text-[#64748b]">{row.detail}</span>
                </span>
                <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: row.dot }} />
              </label>
            </li>
          );
        })}
      </ul>

      <div className="mt-4 flex items-start gap-2.5 rounded-xl bg-[#f0fdf4] px-4 py-3">
        <span className="mt-1.5 size-2 shrink-0 rounded-full bg-[#16a34a]" />
        <p className="text-sm leading-relaxed text-[#15803d]">
          <span className="font-semibold">
            Dự kiến tiếp cận toàn bộ {households.toLocaleString("vi-VN")} hộ dân
          </span>
          <br />
          Ưu tiên {priorityHouseholds.toLocaleString("vi-VN")} hộ ở vùng nguy cơ rất cao
        </p>
      </div>
    </div>
  );
}

/* ─────────────────────────── Compose controls ─────────────────────────── */

function RadioPill({ checked, onSelect, label }: { checked: boolean; onSelect: () => void; label: string }) {
  return (
    <button type="button" onClick={onSelect} className="inline-flex items-center gap-2 text-base text-[#334155]">
      <span
        className={`grid size-5 place-items-center rounded-full border-2 transition-colors ${
          checked ? "border-[#4f46e5]" : "border-[#cbd5e1]"
        }`}
      >
        {checked && <span className="size-2.5 rounded-full bg-[#4f46e5]" />}
      </span>
      {label}
    </button>
  );
}

function VoicePicker({
  voice,
  recordings,
  onChange,
  onRecord,
}: {
  voice: BroadcastVoice;
  recordings: VoiceRecording[];
  onChange: (voice: BroadcastVoice) => void;
  onRecord: () => void;
}) {
  return (
    <div className="inline-flex items-center gap-2">
      <div className="relative">
        <select
          value={voiceToValue(voice)}
          onChange={(event) => onChange(valueToVoice(event.target.value))}
          aria-label="Chọn giọng phát"
          className="h-9 appearance-none rounded-lg border border-[#cbd5e1] bg-white pr-8 pl-3 text-sm font-medium text-[#334155] outline-none focus:border-[#6366f1]"
        >
          <option value="tts:kinh">Giọng Kinh (AI đọc)</option>
          <option value="tts:hmong">Giọng H&apos;Mông (AI đọc)</option>
          {recordings.length > 0 && (
            <optgroup label="Giọng đã thu">
              {recordings.map((rec) => (
                <option key={rec.id} value={`rec:${rec.id}`}>
                  {rec.name}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <CaretDown
          size={14}
          weight="bold"
          className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[#94a3b8]"
        />
      </div>
      <button
        type="button"
        onClick={onRecord}
        title="Thu âm giọng của bạn"
        className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[#cbd5e1] bg-white px-3 text-sm font-semibold text-[#4f46e5] transition-colors hover:bg-[#eef2ff]"
      >
        <Microphone weight="fill" size={15} /> Thu âm
      </button>
    </div>
  );
}

// "Nghe thử" player. Audio-backed voices (saved recordings + the H'Mông sample) play a real
// <audio> element; the Kinh voice is read aloud live via the Web Speech API.
function NghePlayer({
  voice,
  voiceLabel,
  message,
}: {
  voice: BroadcastVoice;
  voiceLabel: string;
  message: string;
}) {
  const audioUrl = audioUrlForVoice(voice);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentMs, setCurrentMs] = useState(0);
  const [durationMs, setDurationMs] = useState(0);
  const ttsTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const ttsStart = useRef(0);

  // Rough spoken length of the message for the TTS progress estimate (~14 chars/second).
  const ttsEstimateMs = Math.max(2000, Math.round((message.length / 14) * 1000));

  const stopAll = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
    if (ttsTimer.current) clearInterval(ttsTimer.current);
    ttsTimer.current = null;
    setPlaying(false);
    setProgress(0);
    setCurrentMs(0);
  }, []);

  // Stop any playback / speech when the player unmounts. The parent remounts this via a
  // `key` on the selected voice, so switching voice naturally resets all internal state.
  useEffect(() => () => stopAll(), [stopAll]);

  const toggle = useCallback(() => {
    if (playing) {
      stopAll();
      return;
    }
    if (audioUrl) {
      audioRef.current?.play().catch(() => setPlaying(false));
      return;
    }
    // Kinh voice → live TTS.
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(message);
    utterance.lang = "vi-VN";
    const viVoice = window.speechSynthesis.getVoices().find((v) => v.lang?.toLowerCase().startsWith("vi"));
    if (viVoice) utterance.voice = viVoice;
    utterance.onend = () => stopAll();
    ttsStart.current = Date.now();
    setPlaying(true);
    setDurationMs(ttsEstimateMs);
    ttsTimer.current = setInterval(() => {
      const elapsed = Date.now() - ttsStart.current;
      setCurrentMs(elapsed);
      setProgress(Math.min(0.99, elapsed / ttsEstimateMs));
    }, 100);
    window.speechSynthesis.speak(utterance);
  }, [playing, audioUrl, message, ttsEstimateMs, stopAll]);

  return (
    <div className="flex items-center gap-4 rounded-xl border border-[#e2e8f0] bg-[#f8fafc] px-4 py-3">
      <button
        type="button"
        onClick={toggle}
        aria-label={playing ? "Dừng nghe thử" : "Nghe thử"}
        className="grid size-11 shrink-0 place-items-center rounded-full bg-[#4f46e5] text-white transition-colors hover:bg-[#4338ca]"
      >
        {playing ? <Pause weight="fill" size={20} /> : <Play weight="fill" size={20} className="ml-0.5" />}
      </button>
      <div className="min-w-0 flex-1">
        <WaveBars progress={progress} />
        <p className="mt-1 truncate text-xs text-[#94a3b8]">{voiceLabel}</p>
      </div>
      <span className="w-12 shrink-0 text-right font-mono text-sm tabular-nums text-[#64748b]">
        {formatClock(playing ? currentMs : durationMs)}
      </span>
      {audioUrl && (
        <audio
          ref={audioRef}
          src={audioUrl}
          preload="metadata"
          onLoadedMetadata={(event) => {
            const seconds = event.currentTarget.duration;
            if (Number.isFinite(seconds)) setDurationMs(seconds * 1000);
          }}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onTimeUpdate={(event) => {
            const el = event.currentTarget;
            if (el.duration) {
              setProgress(el.currentTime / el.duration);
              setCurrentMs(el.currentTime * 1000);
            }
          }}
          onEnded={() => {
            setPlaying(false);
            setProgress(0);
            setCurrentMs(0);
          }}
        />
      )}
    </div>
  );
}

/* ─────────────────────── Saved voices & history ─────────────────────── */

function SavedVoices({ recordings, onRecord }: { recordings: VoiceRecording[]; onRecord: () => void }) {
  return (
    <section className="mt-8">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-[#0f172a]">Giọng nói đã lưu</h2>
        <button
          type="button"
          onClick={onRecord}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#4f46e5] px-4 text-sm font-semibold text-white transition-colors hover:bg-[#4338ca]"
        >
          <Microphone weight="fill" size={16} /> Thu âm mới
        </button>
      </div>
      {recordings.length === 0 ? (
        <div className="mt-4 grid place-items-center rounded-2xl border border-dashed border-[#cbd5e1] bg-white px-6 py-10 text-center">
          <Microphone size={36} weight="thin" className="text-[#cbd5e1]" />
          <p className="mt-3 max-w-sm text-base text-[#475569]">
            Chưa có bản ghi nào. Thu sẵn giọng của bạn để phát trên loa mà không cần đọc trực tiếp mỗi lần.
          </p>
        </div>
      ) : (
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {recordings.map((rec) => (
            <SavedVoiceRow key={rec.id} recording={rec} />
          ))}
        </ul>
      )}
    </section>
  );
}

function SavedVoiceRow({ recording }: { recording: VoiceRecording }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [renaming, setRenaming] = useState(false);

  return (
    <li className="flex items-center gap-3 rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white px-4 py-3.5 shadow-[0_0.4rem_1.2rem_rgb(15_23_42_/_4%)]">
      <button
        type="button"
        onClick={() => {
          const el = audioRef.current;
          if (!el) return;
          if (playing) {
            el.pause();
            el.currentTime = 0;
          } else {
            el.play().catch(() => setPlaying(false));
          }
        }}
        aria-label={playing ? "Dừng" : `Nghe ${recording.name}`}
        className="grid size-10 shrink-0 place-items-center rounded-full bg-[#eef2ff] text-[#4f46e5] transition-colors hover:bg-[#e0e7ff]"
      >
        {playing ? <Pause weight="fill" size={18} /> : <Play weight="fill" size={18} className="ml-0.5" />}
      </button>

      <div className="min-w-0 flex-1">
        {renaming ? (
          <form
            action={renameRecordingAction}
            onSubmit={() => setRenaming(false)}
            className="flex items-center gap-2"
          >
            <input type="hidden" name="id" value={recording.id} />
            <input
              name="name"
              defaultValue={recording.name}
              autoFocus
              maxLength={80}
              className="h-9 w-full rounded-md border border-[#cbd5e1] px-2 text-sm outline-none focus:border-[#6366f1]"
            />
            <button type="submit" className="text-sm font-semibold text-[#4f46e5]">
              Lưu
            </button>
          </form>
        ) : (
          <>
            <p className="truncate text-base font-semibold text-[#0f172a]">{recording.name}</p>
            <p className="text-xs text-[#94a3b8]">
              {formatClock(recording.durationMs)} · {formatDateTime(recording.createdAt)}
            </p>
          </>
        )}
      </div>

      {!renaming && (
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => setRenaming(true)}
            aria-label={`Đổi tên ${recording.name}`}
            className="grid size-9 place-items-center rounded-lg text-[#475569] transition-colors hover:bg-[#eef2ff] hover:text-[#4f46e5]"
          >
            <PencilSimple size={17} />
          </button>
          <form
            action={removeRecording}
            onSubmit={(event) => {
              if (!window.confirm(`Xóa bản ghi “${recording.name}”?`)) event.preventDefault();
            }}
          >
            <input type="hidden" name="id" value={recording.id} />
            <button
              type="submit"
              aria-label={`Xóa ${recording.name}`}
              className="grid size-9 place-items-center rounded-lg text-[#475569] transition-colors hover:bg-[#fef2f2] hover:text-[#ef4444]"
            >
              <Trash size={17} />
            </button>
          </form>
        </div>
      )}

      <audio
        ref={audioRef}
        src={`/api/recordings/${recording.id}`}
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        className="hidden"
      />
    </li>
  );
}

const STATUS_META: Record<BroadcastRecord["status"], { label: string; className: string }> = {
  draft: { label: "Bản nháp", className: "bg-[#f1f5f9] text-[#475569]" },
  sent: { label: "Đã phát", className: "bg-[#dcfce7] text-[#15803d]" },
  scheduled: { label: "Đã hẹn giờ", className: "bg-[#fef3c7] text-[#b45309]" },
};

function BroadcastHistory({
  broadcasts,
  areaById,
}: {
  broadcasts: BroadcastRecord[];
  areaById: Map<string, AreaOption>;
}) {
  if (broadcasts.length === 0) return null;

  return (
    <section className="mt-8">
      <h2 className="text-xl font-bold text-[#0f172a]">Bản nháp &amp; lịch sử phát</h2>
      <ul className="mt-4 flex flex-col gap-3">
        {broadcasts.map((item) => {
          const meta = STATUS_META[item.status];
          const scope =
            item.areaIds.length === 0
              ? "Tất cả khu vực"
              : item.areaIds.map((id) => areaById.get(id)?.name ?? id).join(", ");
          return (
            <li
              key={item.id}
              className="rounded-2xl border border-[rgb(15_23_42_/_8%)] bg-white px-5 py-4 shadow-[0_0.4rem_1.2rem_rgb(15_23_42_/_4%)]"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${meta.className}`}>
                  {meta.label}
                </span>
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#0f172a]">
                  <MapTrifold size={15} className="text-[#94a3b8]" /> {scope}
                </span>
                <span className="ml-auto inline-flex items-center gap-3 text-xs text-[#64748b]">
                  {item.status === "scheduled" && item.scheduledAt && (
                    <span className="inline-flex items-center gap-1">
                      <Clock size={13} /> {formatDateTime(item.scheduledAt)}
                    </span>
                  )}
                  <span>{formatDateTime(item.createdAt)}</span>
                  <form action={removeBroadcast}>
                    <input type="hidden" name="id" value={item.id} />
                    <button
                      type="submit"
                      aria-label="Xóa"
                      className="grid size-7 place-items-center rounded-md text-[#94a3b8] transition-colors hover:bg-[#fef2f2] hover:text-[#ef4444]"
                    >
                      <Trash size={15} />
                    </button>
                  </form>
                </span>
              </div>
              <p className="mt-2 line-clamp-2 text-sm text-[#475569] whitespace-pre-line">{item.message}</p>
              <p className="mt-1.5 text-xs text-[#94a3b8]">
                {item.channels.length} kênh · {item.recipientCount.toLocaleString("vi-VN")} hộ ·{" "}
                {item.repeat > 1 ? `phát ${item.repeat} lần` : "phát 1 lần"}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* ─────────────────────────── Preview modal ─────────────────────────── */

function PreviewModal({
  alert,
  message,
  areaNames,
  channels,
  voiceLabel,
  voice,
  repeatLabel,
  timing,
  scheduledAt,
  households,
  recipients,
  error,
  pending,
  onConfirm,
  onClose,
}: {
  alert: RadioAlert;
  message: string;
  areaNames: string[];
  channels: BroadcastChannel[];
  voiceLabel: string;
  voice: BroadcastVoice;
  repeatLabel: string;
  timing: "now" | "schedule";
  scheduledAt: string;
  households: number;
  recipients: number;
  error?: string;
  pending: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const channelLabels: Record<BroadcastChannel, string> = {
    loudspeaker: "Loa phát thanh bản",
    sms: "SMS",
    zalo: "Zalo OA",
  };

  return (
    <div
      className="fixed inset-0 z-[1000] grid place-items-center bg-[rgb(15_23_42_/_45%)] p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Xem trước cảnh báo"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-[0_1.5rem_3rem_rgb(15_23_42_/_25%)]">
        <div className="flex items-center justify-between border-b border-[#f1f5f9] px-6 py-4">
          <h2 className="text-xl font-bold text-[#0f172a]">Xem trước &amp; kiểm tra</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="grid size-9 place-items-center rounded-lg text-[#94a3b8] transition-colors hover:bg-[#f1f5f9] hover:text-[#0f172a]"
          >
            <X size={20} />
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">
          <div
            className="rounded-xl border p-4"
            style={{ borderColor: `${alert.tierColor}55`, backgroundColor: `${alert.tierColor}12` }}
          >
            <span
              className="inline-block rounded-md px-2 py-0.5 text-[11px] font-bold tracking-wide text-white uppercase"
              style={{ backgroundColor: alert.tierColor }}
            >
              {alert.tierLabel}
            </span>
            <p className="mt-2 text-base leading-relaxed whitespace-pre-line text-[#1e293b]">{message}</p>
          </div>

          <dl className="mt-5 grid gap-3 text-sm">
            <PreviewRow label="Khu vực nhận tin" value={areaNames.join(", ") || "—"} />
            <PreviewRow label="Kênh phát" value={channels.map((c) => channelLabels[c]).join(", ") || "—"} />
            <PreviewRow label="Giọng phát" value={voiceLabel} />
            <PreviewRow label="Lặp lại" value={repeatLabel} />
            <PreviewRow
              label="Thời điểm"
              value={
                timing === "schedule" && scheduledAt
                  ? `Hẹn giờ · ${formatDateTime(new Date(scheduledAt).getTime())}`
                  : "Phát ngay"
              }
            />
            <PreviewRow
              label="Dự kiến tiếp cận"
              value={`${households.toLocaleString("vi-VN")} hộ dân${
                channels.includes("sms") ? ` · ${recipients.toLocaleString("vi-VN")} SMS` : ""
              }`}
            />
          </dl>

          <div className="mt-5 rounded-xl border border-[#e2e8f0] bg-[#f8fafc] p-4">
            <p className="mb-2 text-sm font-semibold text-[#475569]">Nghe thử trước khi phát</p>
            <NghePlayer key={voiceToValue(voice)} voice={voice} voiceLabel={voiceLabel} message={message} />
          </div>

          {error && (
            <p className="mt-4 flex items-center gap-2 text-sm text-[#dc2626]" role="alert">
              <Warning weight="fill" size={16} /> {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-3 border-t border-[#f1f5f9] px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="h-12 rounded-lg border border-[#cbd5e1] bg-white px-5 text-base font-semibold text-[#475569] transition-colors hover:bg-[#f1f5f9]"
          >
            Quay lại
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="inline-flex h-12 items-center gap-2 rounded-lg bg-[#ef4444] px-6 text-base font-semibold text-white transition-colors hover:bg-[#dc2626] disabled:cursor-wait disabled:opacity-70"
          >
            <Broadcast weight="fill" size={20} />
            {pending ? "Đang phát…" : timing === "schedule" ? "Xác nhận hẹn giờ" : "Phát ngay"}
          </button>
        </div>
      </div>
    </div>
  );
}

function PreviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-32 shrink-0 font-semibold text-[#64748b]">{label}</dt>
      <dd className="flex-1 text-[#1e293b]">{value}</dd>
    </div>
  );
}
