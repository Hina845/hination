import { logStep } from "@/lib/log";

type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

export function currentModel() {
  return process.env.OPENAI_MODEL ?? "gpt-4o-mini";
}

function postChat(baseUrl: string, key: string, messages: ChatMessage[], jsonMode: boolean) {
  return fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`,
    },
    body: JSON.stringify({
      model: currentModel(),
      temperature: 0.3,
      // Some OpenAI-compatible gateways (e.g. Gemini bridges) reject response_format;
      // we retry without it when JSON mode is refused.
      ...(jsonMode ? { response_format: { type: "json_object" } } : {}),
      messages,
    }),
    cache: "no-store",
  });
}

/**
 * Minimal OpenAI-compatible Chat Completions call that asks for a JSON object back.
 * Works with api.openai.com or any compatible gateway via OPENAI_BASE_URL. Falls back
 * to a plain request when the gateway refuses JSON mode. Returns the raw model string
 * (caller parses it — it may still be wrapped in prose/code fences).
 */
export async function chatJSON(messages: ChatMessage[]): Promise<string> {
  const baseUrl = (process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1").replace(/\/+$/, "");
  const key = process.env.OPENAI_API_KEY;
  if (!key) {
    throw new Error("OPENAI_API_KEY chưa được cấu hình");
  }

  logStep("openai", "→ chat/completions", { baseUrl, model: currentModel(), jsonMode: true });
  let response = await postChat(baseUrl, key, messages, true);

  // Retry once without JSON mode if the gateway rejected that parameter.
  if (!response.ok && (response.status === 400 || response.status === 422)) {
    const detail = await response.text().catch(() => "");
    logStep("openai", "JSON mode refused — retrying without response_format", { status: response.status, detail: detail.slice(0, 200) });
    response = await postChat(baseUrl, key, messages, false);
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`OpenAI lỗi ${response.status}: ${detail.slice(0, 200)}`);
  }

  const data = (await response.json()) as { choices?: { message?: { content?: string } }[] };
  const content = data.choices?.[0]?.message?.content;
  if (!content) {
    throw new Error("OpenAI không trả về nội dung");
  }
  logStep("openai", "← response", { status: response.status, chars: content.length });
  return content;
}
