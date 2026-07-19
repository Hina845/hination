// Pure type shared between the broadcast server helpers (src/lib/broadcasts) and the
// radio studio client UI. No server-only imports so it stays out of the client bundle.

export type BroadcastChannel = "loudspeaker" | "sms" | "zalo";
export type BroadcastStatus = "draft" | "sent" | "scheduled";

// The voice the message is read in: an AI TTS voice, or one of the chief's own saved
// recordings referenced by id. Stored as a short tag so the log is self-describing.
export type BroadcastVoice =
  | { kind: "tts"; id: "kinh" | "hmong" }
  | { kind: "recording"; recordingId: number };

export type Broadcast = {
  id: number;
  status: BroadcastStatus;
  areaIds: string[]; // targeted forecast area ids; empty = every villager the chief owns
  message: string;
  channels: BroadcastChannel[];
  voice: BroadcastVoice;
  repeat: number; // number of times the alert is played (1 = once)
  repeatGapMinutes: number; // minutes between repeats (0 when repeat === 1)
  scheduledAt: number | null; // epoch ms for a scheduled send; null = "phát ngay"
  recipientCount: number; // SMS reach at send time
  createdAt: number;
};
