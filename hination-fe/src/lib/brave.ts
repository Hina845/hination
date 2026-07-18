import { logStep } from "@/lib/log";
import type { NewsSource } from "@/types/area-brief";

const BRAVE_BASE_URL = process.env.BRAVE_SEARCH_BASE_URL ?? "https://api.search.brave.com/res/v1/web/search";

type BraveResult = {
  title?: string;
  url?: string;
  description?: string;
  age?: string;
  page_age?: string;
  profile?: { name?: string };
  meta_url?: { hostname?: string };
};

/**
 * Fetch fresh Vietnamese news / state alerts for an area via the Brave Search API.
 * Returns real, linkable results (never fabricated). Throws when the key is missing
 * or the request fails so the caller can decide whether to fall back to a cached brief.
 */
export async function searchNews(query: string, count = 8): Promise<NewsSource[]> {
  const key = process.env.BRAVE_SEARCH_API_KEY;
  if (!key) {
    throw new Error("BRAVE_SEARCH_API_KEY chưa được cấu hình");
  }

  const params = new URLSearchParams({
    q: query,
    count: String(count),
    search_lang: "vi",
    freshness: "pw", // past week — keeps the brief tied to recent reporting
    text_decorations: "false",
    safesearch: "moderate",
  });
  // `country` must be one of Brave's supported markets — Vietnam (vn) is NOT in that
  // list and makes Brave reject the whole request with HTTP 422. We rely on the
  // Vietnamese query + search_lang=vi for locale instead. Allow an explicit override
  // via env only if it's a supported code.
  const country = process.env.BRAVE_SEARCH_COUNTRY;
  if (country) params.set("country", country);

  logStep("brave", "→ searching", { query, count, country: country ?? "(default)" });
  const response = await fetch(`${BRAVE_BASE_URL}?${params.toString()}`, {
    headers: {
      Accept: "application/json",
      "Accept-Encoding": "gzip",
      "X-Subscription-Token": key,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    // Surface Brave's validation detail so a 422 tells us exactly which param it rejected.
    const detail = await response.text().catch(() => "");
    throw new Error(`Brave Search lỗi ${response.status}${detail ? `: ${detail.slice(0, 300)}` : ""}`);
  }

  const data = (await response.json()) as { web?: { results?: BraveResult[] } };
  const results = Array.isArray(data.web?.results) ? data.web!.results! : [];

  const sources = results
    .slice(0, count)
    .map((result) => ({
      title: (result.title ?? "").trim(),
      url: result.url ?? "",
      publisher: result.profile?.name ?? result.meta_url?.hostname ?? "",
      age: result.age ?? result.page_age,
      snippet: result.description,
    }))
    .filter((source) => Boolean(source.url && source.title));

  logStep("brave", "← results", { status: response.status, found: sources.length, publishers: sources.map((s) => s.publisher) });
  return sources;
}
