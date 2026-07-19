"use client";

import { ArrowClockwise, Microphone, Play, Stop, Warning, X } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { startTransition, useActionState } from "react";

import WaveBars from "@/components/WaveBars";
import { saveRecording, type RecordingFormState } from "@/app/radio/actions";
import type { VoiceRecording } from "@/types/recording";

type Phase = "idle" | "recording" | "recorded";

const emptyState: RecordingFormState = {};

// Pick the first MediaRecorder mime the browser supports. Chrome/Firefox give webm/opus;
// Safari falls back to mp4. Empty string lets the browser choose its own default.
function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

function formatClock(ms: number): string {
  const total = Math.round(ms / 1000);
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

/**
 * Capture the chief's own voice for reuse as the spoken alert. Records via MediaRecorder,
 * lets them play it back, name it, and saves the clip to their account (server action
 * `saveRecording`). On success the parent receives the new recording metadata and can
 * select it as the broadcast voice immediately.
 */
export default function VoiceRecorderModal({
  onClose,
  onSaved,
  defaultName,
}: {
  onClose: () => void;
  onSaved: (recording: VoiceRecording) => void;
  defaultName?: string;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [recordedMs, setRecordedMs] = useState(0); // final clip length, for display after stop
  const [level, setLevel] = useState(0);
  const [name, setName] = useState(defaultName ?? "");
  const [state, dispatch, saving] = useActionState(saveRecording, emptyState);

  // Refs for the imperative recording pipeline — none of these should trigger re-renders.
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const blobRef = useRef<Blob | null>(null);
  const durationRef = useRef(0);
  const startedAtRef = useRef(0);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const previewRef = useRef<HTMLAudioElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  const teardownStream = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (tickRef.current) clearInterval(tickRef.current);
    tickRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
  }, []);

  // Full cleanup on unmount: stop the mic, drop the analyser, revoke the preview URL.
  useEffect(() => {
    return () => {
      teardownStream();
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, [teardownStream]);

  // Bubble the saved recording up once the server action returns an id.
  useEffect(() => {
    if (state.savedId) {
      onSaved({
        id: state.savedId,
        name: name.trim(),
        mime: blobRef.current?.type || "audio/webm",
        durationMs: durationRef.current,
        createdAt: Date.now(),
      });
    }
  }, [state.savedId, name, onSaved]);

  const startRecording = useCallback(async () => {
    setPermissionError(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setPermissionError("Trình duyệt không hỗ trợ ghi âm.");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setPermissionError("Không truy cập được micro. Vui lòng cấp quyền và thử lại.");
      return;
    }

    streamRef.current = stream;
    chunksRef.current = [];
    blobRef.current = null;

    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorderRef.current = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || mimeType || "audio/webm" });
      blobRef.current = blob;
      durationRef.current = Date.now() - startedAtRef.current;
      setRecordedMs(durationRef.current);
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = URL.createObjectURL(blob);
      if (previewRef.current) previewRef.current.src = previewUrlRef.current;
      teardownStream();
      setLevel(0);
      setPhase("recorded");
    };

    // Live level meter so the chief can see the mic is picking up their voice.
    const audioCtx = new AudioContext();
    audioCtxRef.current = audioCtx;
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    const buffer = new Uint8Array(analyser.frequencyBinCount);
    const sample = () => {
      analyser.getByteTimeDomainData(buffer);
      let peak = 0;
      for (const value of buffer) peak = Math.max(peak, Math.abs(value - 128));
      setLevel(Math.min(1, peak / 90));
      rafRef.current = requestAnimationFrame(sample);
    };
    sample();

    startedAtRef.current = Date.now();
    setElapsed(0);
    tickRef.current = setInterval(() => setElapsed(Date.now() - startedAtRef.current), 200);
    recorder.start();
    setPhase("recording");
  }, [teardownStream]);

  const stopRecording = useCallback(() => {
    recorderRef.current?.state === "recording" && recorderRef.current.stop();
  }, []);

  const reset = useCallback(() => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    blobRef.current = null;
    durationRef.current = 0;
    setRecordedMs(0);
    setElapsed(0);
    setPhase("idle");
  }, []);

  const handleSave = useCallback(() => {
    const blob = blobRef.current;
    if (!blob || !name.trim()) return;
    const extension = (blob.type.split("/")[1] ?? "webm").split(";")[0];
    const form = new FormData();
    form.append("audio", blob, `recording.${extension}`);
    form.append("name", name.trim());
    form.append("durationMs", String(durationRef.current));
    // Called from an onClick handler, so wrap dispatch in a transition (see RadioStudio).
    startTransition(() => dispatch(form));
  }, [name, dispatch]);

  return (
    <div
      className="fixed inset-0 z-[1100] grid place-items-center bg-[rgb(15_23_42_/_45%)] p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Thu âm giọng nói"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && phase !== "recording") onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-2xl bg-white p-7 shadow-[0_1.5rem_3rem_rgb(15_23_42_/_25%)]">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-xl font-bold text-[#0f172a]">Thu âm giọng của bạn</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={phase === "recording"}
            aria-label="Đóng"
            className="grid size-9 place-items-center rounded-lg text-[#94a3b8] transition-colors hover:bg-[#f1f5f9] hover:text-[#0f172a] disabled:opacity-40"
          >
            <X size={20} />
          </button>
        </div>
        <p className="mb-5 text-sm text-[#64748b]">
          Đọc nội dung cảnh báo bằng giọng của bạn để phát trên loa. Bản ghi được lưu lại để dùng cho các lần sau.
        </p>

        {/* Visualizer / clock */}
        <div className="rounded-xl border border-[#e2e8f0] bg-[#f8fafc] px-5 py-4">
          <div className="flex items-center gap-4">
            <span
              className={`grid size-11 shrink-0 place-items-center rounded-full ${
                phase === "recording" ? "animate-pulse bg-[#ef4444] text-white" : "bg-[#eef2ff] text-[#4f46e5]"
              }`}
            >
              <Microphone weight="fill" size={22} />
            </span>
            <WaveBars className="flex-1" progress={0} live={phase === "recording" ? level : 0} />
            <span className="w-14 text-right font-mono text-base tabular-nums text-[#334155]">
              {formatClock(phase === "recorded" ? recordedMs : elapsed)}
            </span>
          </div>
        </div>

        {/* Hidden element that plays back the recorded clip on demand. */}
        <audio ref={previewRef} preload="auto" className="hidden" />

        {permissionError && (
          <p className="mt-4 flex items-center gap-2 text-sm text-[#dc2626]" role="alert">
            <Warning weight="fill" size={16} /> {permissionError}
          </p>
        )}

        {/* Controls */}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          {phase === "idle" && (
            <button
              type="button"
              onClick={startRecording}
              className="inline-flex h-12 flex-1 items-center justify-center gap-2 rounded-lg bg-[#ef4444] px-5 text-base font-semibold text-white transition-colors hover:bg-[#dc2626]"
            >
              <Microphone weight="fill" size={20} /> Bắt đầu thu
            </button>
          )}
          {phase === "recording" && (
            <button
              type="button"
              onClick={stopRecording}
              className="inline-flex h-12 flex-1 items-center justify-center gap-2 rounded-lg bg-[#0f172a] px-5 text-base font-semibold text-white transition-colors hover:bg-[#1e293b]"
            >
              <Stop weight="fill" size={20} /> Dừng thu
            </button>
          )}
          {phase === "recorded" && (
            <>
              <button
                type="button"
                onClick={() => previewRef.current?.play()}
                className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-[#cbd5e1] bg-white px-5 text-base font-semibold text-[#0f172a] transition-colors hover:bg-[#f1f5f9]"
              >
                <Play weight="fill" size={18} /> Nghe lại
              </button>
              <button
                type="button"
                onClick={reset}
                className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-[#cbd5e1] bg-white px-5 text-base font-semibold text-[#475569] transition-colors hover:bg-[#f1f5f9]"
              >
                <ArrowClockwise weight="bold" size={18} /> Thu lại
              </button>
            </>
          )}
        </div>

        {/* Name + save — only meaningful once there's a clip. */}
        {phase === "recorded" && (
          <div className="mt-5 grid gap-2">
            <label htmlFor="recording-name" className="text-sm font-semibold text-[#475569]">
              Tên bản ghi
            </label>
            <input
              id="recording-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={80}
              placeholder="VD: Cảnh báo lũ quét – giọng trưởng bản"
              className="h-12 w-full rounded-[10px] border border-[#cbd5e1] bg-white px-4 text-base text-[#333] outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#94a3b8] focus:border-[#6366f1] focus:shadow-[0_0_0_3px_rgb(99_102_241_/_15%)]"
            />
            {state.error && (
              <p className="text-sm text-[#dc2626]" role="alert">
                {state.error}
              </p>
            )}
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !name.trim()}
              className="mt-1 inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-[#4f46e5] px-6 text-base font-semibold text-white transition-colors hover:bg-[#4338ca] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? "Đang lưu…" : "Lưu bản ghi"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
