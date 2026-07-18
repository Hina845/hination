import { searchNews } from "@/lib/brave";
import { clampPredictLevel, overallLevel, reduceModelLevel } from "@/lib/danger-score";
import { db } from "@/lib/db";
import { logError, logStep } from "@/lib/log";
import { chatJSON, currentModel } from "@/lib/openai";
import type { AreaBrief, AreaBriefInput, NewsSource } from "@/types/area-brief";

// News + AI summary are cached in SQLite (persisted in the frontend-data volume, so
// they survive a `docker compose up --build`). Default 12h so a rebuild/restart within
// the same half-day serves the cached copy instead of re-hitting Brave + OpenAI; this
// matches the 12h warm cadence (see brief-worker.ts / instrumentation.ts). Override with
// AREA_BRIEF_TTL_MINUTES.
const TTL_MS = (Number(process.env.AREA_BRIEF_TTL_MINUTES) || 720) * 60 * 1000;

const DISASTER_VI: Record<string, string> = {
  flood: "mưa lũ, ngập lụt",
  landslide: "sạt lở đất",
  storm: "mưa bão",
  wildfire: "cháy rừng, nắng nóng",
  wind: "gió mạnh, giông lốc",
};

type BriefRow = {
  area_id: string;
  brief_date: string;
  headline: string;
  summary: string;
  sources: string;
  model: string | null;
  generated_at: number;
  predict_level: number;
};

function hazardText(input: AreaBriefInput) {
  const key = input.danger?.dominantDisaster;
  return (key && DISASTER_VI[key]) || "thiên tai";
}

function readRow(areaId: string, date: string): AreaBrief | null {
  const row = db
    .prepare("SELECT * FROM area_briefs WHERE area_id = ? AND brief_date = ?")
    .get(areaId, date) as BriefRow | undefined;
  if (!row) return null;

  let sources: NewsSource[] = [];
  try {
    sources = JSON.parse(row.sources) as NewsSource[];
  } catch {
    sources = [];
  }

  return {
    areaId: row.area_id,
    date: row.brief_date,
    headline: row.headline,
    summary: row.summary,
    sources,
    model: row.model,
    generatedAt: row.generated_at,
    cached: true,
  };
}

/**
 * Read the stored AI prediction (0–2) for every area on a given day, keyed by area id.
 * Used by the server-rendered map to recolor areas by their combined overall level
 * without generating anything on the request path.
 */
export function readPredictLevelsForDate(date: string): Map<string, number> {
  const rows = db
    .prepare("SELECT area_id, predict_level FROM area_briefs WHERE brief_date = ?")
    .all(date) as { area_id: string; predict_level: number }[];
  return new Map(rows.map((row) => [row.area_id, clampPredictLevel(row.predict_level ?? 0)]));
}

function buildQuery(input: AreaBriefInput) {
  return `${input.name} Điện Biên cảnh báo ${hazardText(input)} thời tiết thiên tai`;
}

/**
 * Parse the model's reply into { headline, summary }. Tolerates JSON wrapped in
 * ```code fences``` or surrounded by prose (common when the gateway ignores JSON mode).
 */
function extractJson(raw: string): { headline?: unknown; summary?: unknown; predictLevel?: unknown; relevantSources?: unknown } {
  const cleaned = raw.replace(/```(?:json)?/gi, "").trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    // Fall through to brace extraction.
  }
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start !== -1 && end > start) {
    try {
      return JSON.parse(cleaned.slice(start, end + 1));
    } catch {
      // Give up — caller uses fallbacks.
    }
  }
  return {};
}

async function summarize(
  input: AreaBriefInput,
  sources: NewsSource[],
): Promise<{ headline: string; summary: string; predictLevel: number; sources: NewsSource[] }> {
  const context = sources.length
    ? sources
        .map(
          (source, index) =>
            `(${index + 1}) ${source.title} — ${source.publisher}${source.age ? ` [${source.age}]` : ""}\n${source.snippet ?? ""}`,
        )
        .join("\n\n")
    : "Không tìm thấy bản tin liên quan trong thời gian gần đây.";

  // The model's own forecast level is deliberately NOT provided: both the summary and
  // the predicted level must come ONLY from the fetched news, so the AI signal stays
  // independent of the API level it will later be combined with.
  const system = [
    "Bạn là trợ lý truyền thông khẩn cấp cho chính quyền xã tại tỉnh Điện Biên, Việt Nam.",
    "Nhiệm vụ: tổng hợp các bản tin thời sự (VTV, báo địa phương, Đài Khí tượng Thủy văn, thông báo cơ quan nhà nước) thành một bản tin ngắn để cán bộ đọc/phát cho người dân trong xã.",
    "CHỈ dùng thông tin có trong các bản tin được cung cấp bên dưới; TUYỆT ĐỐI không bịa đặt số liệu hay sự kiện, không suy đoán ngoài bản tin. Nếu không có bản tin liên quan, hãy nói rõ là chưa có tin mới và đưa khuyến cáo phòng tránh chung.",
    "LỌC NGUỒN TIN: Kết quả tìm kiếm thường lẫn bản tin về tỉnh/thành phố hoặc quốc gia khác không liên quan. CHỈ coi là liên quan những bản tin nói trực tiếp về khu vực này, về tỉnh Điện Biên, hoặc về sự kiện thiên tai ảnh hưởng trực tiếp tới khu vực. Bản tin về địa phương khác (tỉnh/thành/nước khác) hoặc chủ đề không liên quan tới thiên tai của khu vực => KHÔNG liên quan, phải loại bỏ. Chỉ dùng các bản tin liên quan để viết summary và đánh giá predictLevel.",
    "Giọng điệu bình tĩnh, rõ ràng, ưu tiên hành động cụ thể người dân cần làm.",
    'Đánh giá "predictLevel" — mức độ nguy hiểm CHỈ dựa trên nội dung các bản tin LIÊN QUAN, KHÔNG dựa vào bất kỳ dự báo mô hình nào. Dùng số nguyên: 0 = bản tin không cho thấy nguy hiểm hoặc không có bản tin liên quan; 1 = bản tin nhắc đến cảnh báo/nguy cơ ở mức vừa phải; 2 = bản tin đưa tin thiên tai nghiêm trọng, khẩn cấp đang hoặc sắp xảy ra tại khu vực. Chỉ được là 0, 1 hoặc 2.',
    'Trả về JSON đúng dạng: {"headline": string, "summary": string, "predictLevel": number, "relevantSources": number[]}. "headline" là tiêu đề "việc cần làm" ngắn gọn, tối đa 90 ký tự. "summary" gồm 2-4 câu hướng dẫn cụ thể bằng tiếng Việt. "relevantSources" là mảng số thứ tự (ví dụ [1, 3]) của CHỈ những bản tin liên quan tới khu vực/tỉnh Điện Biên theo đánh số ở dưới; nếu không có bản tin nào liên quan thì trả về [].',
  ].join("\n");

  const user = [
    `Khu vực: ${input.name}${input.adminCode ? ` (mã ${input.adminCode})` : ""}, ngày ${input.date}.`,
    "",
    "Bản tin thu thập được:",
    context,
  ].join("\n");

  const raw = await chatJSON([
    { role: "system", content: system },
    { role: "user", content: user },
  ]);

  const parsed = extractJson(raw);
  const headlineText = String(parsed.headline ?? "").trim();
  const summaryText = String(parsed.summary ?? "").trim();
  const predictLevel = clampPredictLevel(Number(parsed.predictLevel));
  if (!headlineText && !summaryText) {
    logStep("area-brief", "⚠ model reply not parseable as JSON — using fallback", { preview: raw.slice(0, 120) });
  }

  // Keep only the sources the model flagged as relevant to this area / Điện Biên.
  // When the field is present (even an empty array) we trust it; when it's missing
  // entirely (e.g. the gateway dropped it) we keep every source rather than blanking
  // the news section on a parse hiccup.
  let relevantSources = sources;
  if (Array.isArray(parsed.relevantSources) && sources.length) {
    const keep = new Set(
      (parsed.relevantSources as unknown[])
        .map((value) => Number(value) - 1)
        .filter((index) => Number.isInteger(index) && index >= 0 && index < sources.length),
    );
    relevantSources = sources.filter((_, index) => keep.has(index));
    logStep("area-brief", "⚙ filtered sources by relevance", { before: sources.length, after: relevantSources.length });
  }

  const headline = headlineText || `Theo dõi cảnh báo ${hazardText(input)}`;
  const summary =
    summaryText ||
    "Chưa có bản tin mới. Người dân theo dõi thông báo của chính quyền địa phương và Đài Khí tượng Thủy văn, chủ động phòng tránh theo hướng dẫn.";

  return { headline: headline.slice(0, 160), summary: summary.slice(0, 900), predictLevel, sources: relevantSources };
}

/**
 * Return the shared AI news brief for an area+day. Serves the DB copy when it is
 * newer than the TTL (default 12h); otherwise fetches fresh news via Brave,
 * summarizes with OpenAI, upserts, and returns. On generation failure a still-cached
 * copy is returned (stale) rather than erroring.
 */
export async function getAreaBrief(input: AreaBriefInput, forceRefresh = false): Promise<AreaBrief> {
  const modelLevel = input.danger?.level ?? 1;
  logStep("area-brief", "1. request", { area: input.name, areaId: input.areaId, date: input.date, forceRefresh, modelLevel });

  const existing = readRow(input.areaId, input.date);
  if (existing) {
    const ageMin = Math.round((Date.now() - existing.generatedAt) / 60000);
    logStep("area-brief", "2. cache hit", { ageMinutes: ageMin, ttlMinutes: TTL_MS / 60000, sources: existing.sources.length });
  } else {
    logStep("area-brief", "2. cache miss");
  }

  if (existing && !forceRefresh && Date.now() - existing.generatedAt < TTL_MS) {
    logStep("area-brief", "3. serving cached copy (fresh, no refetch)");
    return existing;
  }
  logStep("area-brief", "3. generating fresh brief", { reason: forceRefresh ? "manual refresh" : existing ? "stale" : "no cache" });

  try {
    // A search failure shouldn't sink the whole brief — summarize with whatever we have.
    const query = buildQuery(input);
    const sources = await searchNews(query).catch((error) => {
      logError("area-brief", "4. news search failed — continuing with no sources", error);
      return [] as NewsSource[];
    });
    logStep("area-brief", "5. summarizing with AI", { sources: sources.length, model: currentModel() });
    const { headline, summary, predictLevel, sources: relevantSources } = await summarize(input, sources);
    const overall = overallLevel(modelLevel, predictLevel);
    logStep("area-brief", "6. summary ready", { headline, predictLevel, modelLevel, reduced: reduceModelLevel(modelLevel), overall });
    const model = currentModel();
    const generatedAt = Date.now();

    db.prepare(
      `INSERT INTO area_briefs (area_id, brief_date, headline, summary, sources, model, generated_at, predict_level)
       VALUES (@area_id, @brief_date, @headline, @summary, @sources, @model, @generated_at, @predict_level)
       ON CONFLICT(area_id, brief_date) DO UPDATE SET
         headline = @headline,
         summary = @summary,
         sources = @sources,
         model = @model,
         generated_at = @generated_at,
         predict_level = @predict_level`,
    ).run({
      area_id: input.areaId,
      brief_date: input.date,
      headline,
      summary,
      sources: JSON.stringify(relevantSources),
      model,
      generated_at: generatedAt,
      predict_level: predictLevel,
    });
    logStep("area-brief", "7. saved to database (shared across accounts)");

    return { areaId: input.areaId, date: input.date, headline, summary, sources: relevantSources, model, generatedAt, cached: false };
  } catch (error) {
    logError("area-brief", "generation failed", error);
    // On a passive hover, prefer showing a stale copy over an error. But on an explicit
    // manual refresh the user is waiting for new content — surface the error so they see
    // why it didn't update instead of silently returning the same old brief.
    if (existing && !forceRefresh) {
      logStep("area-brief", "falling back to stale cached copy");
      return existing;
    }
    throw error;
  }
}
