import { logStep } from "@/lib/log";

export type SmsRecipient = { name: string; phone: string };

export type SmsResult = { sent: number; provider: "stub" };

/**
 * Send an emergency SMS to a set of villagers.
 *
 * No SMS provider is wired up yet, so this stub only logs and simulates the send so
 * the Manage flow is testable end to end. When a real provider is added (e.g. an
 * `SMS_API_KEY` + `fetch`, mirroring src/lib/brave.ts), replace the body below and
 * keep this signature.
 */
export async function sendEmergencySms(recipients: SmsRecipient[], message: string): Promise<SmsResult> {
  const phones = recipients.map((recipient) => recipient.phone).filter(Boolean);
  logStep("sms", "→ gửi SMS khẩn (stub)", { count: phones.length, message });
  return { sent: phones.length, provider: "stub" };
}
