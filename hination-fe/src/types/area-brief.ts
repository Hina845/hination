// Pure types shared between the server pipeline (src/lib/*) and the client card
// (src/components/AreaBriefCard). Keep this file free of any server-only imports
// so it never drags better-sqlite3 / node APIs into the client bundle.

export type NewsSource = {
  title: string;
  url: string;
  publisher: string;
  age?: string;
  snippet?: string;
};

export type AreaBriefDanger = {
  level?: number;
  dominantDisaster?: string;
  message?: string;
  overallRisk?: number;
};

export type AreaBriefInput = {
  areaId: string;
  name: string;
  adminCode?: string;
  date: string; // YYYY-MM-DD of the forecast day
  danger?: AreaBriefDanger;
};

export type AreaBrief = {
  areaId: string;
  date: string;
  headline: string;
  summary: string;
  sources: NewsSource[];
  model: string | null;
  generatedAt: number; // epoch ms
  cached: boolean; // true when served from the DB without regeneration
};
