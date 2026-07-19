// Pure type shared between the recording server helpers (src/lib/recordings) and the
// radio studio client UI. Keep this file free of server-only imports so it never drags
// better-sqlite3 / node APIs into the client bundle.
//
// The audio bytes themselves are NOT carried on this type — they are streamed on demand
// from /api/recordings/[id]. The client only ever holds metadata plus that URL.

export type VoiceRecording = {
  id: number;
  name: string; // chief-given label, e.g. "Cảnh báo lũ – giọng trưởng bản"
  mime: string; // e.g. "audio/webm" or "audio/mp4"
  durationMs: number; // measured length of the clip
  createdAt: number; // epoch ms
};
