// Seed ~10,000 citizen contacts for the village chief (the `admin` user), spread across
// the 45 communes/wards of Điện Biên province in proportion to each unit's real population.
//
// Why this exists: the dashboard's citizen summary, per-area counts, and area-scoped SMS
// all read from the `villagers` table (contacts, no login/password). A fresh DB has none,
// so every area shows 0 and the SMS scoping has nothing to target. This fills the table
// with a realistic population so the map summary, hover cards, blast dropdown, and the
// /manage SMS scopes all show and send meaningful numbers.
//
// Distribution is by **real population cluster ratio**, not uniform: the urban wards
// (Phường Điện Biên Phủ, Mường Thanh) and the Mường Thanh rice valley (Thanh Nưa, Thanh
// An, Thanh Yên, Sam Mứn…) hold most people, while the remote northern mountain communes
// (Sín Thầu, Mường Nhé, Nậm Kè…) are sparse. Weights below are per-unit population in
// thousands, grounded in the 2025 45-unit reorg (province ≈ 657k; units range ~6k–49k,
// Phường Điện Biên Phủ highest, Thanh Nưa ≈ 29k). Sources: Nghị quyết 1661/NQ-UBTVQH15;
// citypopulation.de / Wikipedia district figures.
//
// Data is fully reproducible (fixed-seed PRNG), so re-running — or seeding prod — yields
// the same 10k rows. Run: `pnpm seed:citizens` (from hination-fe/). Idempotent: it clears
// the admin's existing citizens first, then reinserts.

import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { readFileSync } from "node:fs";

import Database from "better-sqlite3";
import bcrypt from "bcryptjs";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const dataDir = join(scriptDir, "..", "data");
const geojsonPath = join(scriptDir, "..", "public", "dien-bien-communes.geojson");

const TARGET = 10_000;
const OWNER_USERNAME = "admin";

// Per-unit population weight (thousands). Keyed by the forecast area id (see
// forecast-area-id.ts). Higher = denser cluster; the 10k citizens are apportioned by
// each unit's share of the total weight. Values approximate the real distribution across
// urban wards, the Mường Thanh valley, district towns, and remote highland communes.
const POPULATION_WEIGHTS = {
  // Urban wards + Mường Thanh valley (densest)
  dien_bien_phu: 49, // Phường Điện Biên Phủ
  commune_19571211: 35, // Phường Mường Thanh
  commune_19571190: 29, // Xã Thanh Nưa
  commune_19571191: 22, // Xã Thanh An
  commune_19571189: 20, // Xã Thanh Yên
  commune_19571196: 18, // Xã Sam Mứn
  commune_19571203: 15, // Xã Núa Ngam
  commune_19571214: 13, // Xã Mường Nhà
  commune_19571213: 11, // Xã Mường Phăng
  commune_19571212: 10, // Xã Mường Pồn
  // District towns / mid-density
  tuan_giao: 24, // Xã Tuần Giáo
  muong_ang: 20, // Xã Mường Ảng
  tua_chua: 16, // Xã Tủa Chùa
  dien_bien_dong: 16, // Xã Na Son (Điện Biên Đông)
  muong_cha: 15, // Xã Mường Chà
  commune_19571224: 14, // Xã Búng Lao
  commune_19571198: 13, // Xã Quài Tở
  commune_19571222: 12, // Xã Chiềng Sinh
  commune_19571215: 12, // Xã Mường Mùn
  commune_19571205: 12, // Xã Nà Tấu
  muong_lay: 12, // Phường Mường Lay
  commune_19571195: 11, // Xã Sáng Nhè
  commune_19571207: 11, // Xã Na Sang
  commune_19571216: 10, // Xã Mường Luân
  // Highland / remote (sparse)
  muong_nhe: 12, // Xã Mường Nhé
  commune_19537915: 11, // Xã Mường Toong
  nam_po: 10, // Xã Si Pa Phìn
  commune_19571200: 10, // Xã Pu Nhi
  commune_19571218: 10, // Xã Mường Lạn
  commune_19537916: 9, // Xã Nậm Kè
  commune_19571208: 9, // Xã Nà Hỳ
  commune_19571209: 9, // Xã Nà Bủng
  commune_19571199: 9, // Xã Pú Nhung
  commune_19571201: 9, // Xã Phình Giàng
  commune_19571186: 9, // Xã Tủa Thàng
  commune_19571192: 9, // Xã Sính Phình
  commune_19571188: 8, // Xã Tìa Dình
  commune_19571197: 8, // Xã Quảng Lâm
  commune_19571202: 8, // Xã Pa Ham
  commune_19571210: 8, // Xã Mường Tùng
  commune_19571184: 8, // Xã Xa Dung
  commune_19571223: 8, // Xã Chà Tở
  commune_19571204: 7, // Xã Nậm Nèn
  commune_19571193: 7, // Xã Sín Chải
  commune_19537811: 6, // Xã Sín Thầu
};

// Deterministic PRNG (mulberry32) so the seed is reproducible across machines and prod.
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(0x0d1e_b1e7);
const pick = (arr) => arr[Math.floor(rand() * arr.length)];
const between = (min, max) => min + Math.floor(rand() * (max - min + 1));

// Surnames reflecting Điện Biên's ethnic mix: Kinh, Thái (Lò, Lường, Quàng, Cà, Tòng),
// and H'Mông (Vàng, Giàng, Sùng, Thào, Mùa, Vừ, Hạng).
const SURNAMES = [
  "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Ngô", "Dương",
  "Lò", "Lò", "Lường", "Quàng", "Quàng", "Cà", "Tòng", "Bạc", "Điêu", "Lỡ",
  "Vàng", "Vàng", "Giàng", "Giàng", "Sùng", "Thào", "Mùa", "Vừ", "Hạng", "Lý", "Sính", "Cứ",
];
const GIVEN_MALE = [
  "Văn An", "Văn Bình", "Văn Cường", "Văn Dũng", "Văn Đức", "Văn Hùng", "Văn Khánh",
  "Văn Long", "Văn Minh", "Văn Nam", "Văn Phong", "Văn Quang", "Văn Sơn", "Văn Tài",
  "Văn Thành", "Văn Tuấn", "Đức Anh", "Quang Huy", "Bá Lâm",
  "A Của", "A Dơ", "A Lử", "A Sùng", "A Vàng", "A Chớ", "A Páo", "A Dế",
];
const GIVEN_FEMALE = [
  "Thị Anh", "Thị Bình", "Thị Cúc", "Thị Duyên", "Thị Hà", "Thị Hoa", "Thị Hương",
  "Thị Lan", "Thị Mai", "Thị Ngọc", "Thị Nhung", "Thị Phượng", "Thị Thu", "Thị Trang",
  "Thị Vân", "Thị Yến", "Thị Mỷ", "Thị Dở", "Thị Sua", "Thị Pàng", "Thị Xia", "Thị Dua",
];
const HAMLET_WORDS = ["Na", "Co", "Pá", "Huổi", "Nậm", "Pom", "Che", "Xa", "Púng", "Hồng"];

function makeName() {
  const surname = pick(SURNAMES);
  const given = rand() < 0.5 ? pick(GIVEN_MALE) : pick(GIVEN_FEMALE);
  return `${surname} ${given}`;
}

// Vietnamese mobile prefixes (Viettel/Mobifone/Vinaphone/Vietnamobile blocks).
const PHONE_PREFIXES = [
  "032", "033", "034", "035", "036", "037", "038", "039", "070", "076", "077", "078",
  "079", "081", "082", "083", "084", "085", "086", "088", "089", "090", "091", "092",
  "093", "094", "096", "097", "098", "099",
];

function makePhone(used) {
  for (;;) {
    let suffix = "";
    for (let i = 0; i < 7; i += 1) suffix += between(0, 9);
    const phone = pick(PHONE_PREFIXES) + suffix;
    if (!used.has(phone)) {
      used.add(phone);
      return phone;
    }
  }
}

function makeAddress(areaName) {
  if (areaName.startsWith("Phường")) return `Tổ dân phố ${between(1, 18)}`;
  return `Bản ${pick(HAMLET_WORDS)} ${between(1, 12)}`;
}

// Apportion TARGET across areas by weight, using largest-remainder so the total is exact.
function apportion(weights, total) {
  const entries = Object.entries(weights);
  const sum = entries.reduce((acc, [, w]) => acc + w, 0);
  const raw = entries.map(([id, w]) => {
    const exact = (w / sum) * total;
    const base = Math.floor(exact);
    return { id, base, remainder: exact - base };
  });
  let assigned = raw.reduce((acc, r) => acc + r.base, 0);
  raw.sort((a, b) => b.remainder - a.remainder);
  for (let i = 0; assigned < total; i = (i + 1) % raw.length) {
    raw[i].base += 1;
    assigned += 1;
  }
  return new Map(raw.map((r) => [r.id, r.base]));
}

function main() {
  // Load the canonical area id → name map from the same geojson the map renders, and
  // verify every weighted id is a real commune (catches typos / reorg drift early).
  const geo = JSON.parse(readFileSync(geojsonPath, "utf-8"));
  const areaNames = new Map();
  for (const feature of geo.features) {
    const p = feature.properties ?? {};
    if (p.kind !== "commune") continue;
    const id = p.forecastId ?? (p.osmRelationId ? `commune_${p.osmRelationId}` : null);
    if (id) areaNames.set(id, p.name);
  }

  const missing = Object.keys(POPULATION_WEIGHTS).filter((id) => !areaNames.has(id));
  if (missing.length) throw new Error(`Weighted ids not found in geojson: ${missing.join(", ")}`);
  const unweighted = [...areaNames.keys()].filter((id) => !(id in POPULATION_WEIGHTS));
  if (unweighted.length) {
    console.warn(`⚠  ${unweighted.length} commune(s) have no weight (will get 0 citizens): ${unweighted.join(", ")}`);
  }

  const db = new Database(join(dataDir, "hination.sqlite"));
  db.pragma("journal_mode = WAL");
  db.pragma("busy_timeout = 5000");

  // Ensure the schema exists so the script runs against a fresh DB too (mirrors db.ts).
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS villagers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      name TEXT NOT NULL,
      phone TEXT NOT NULL,
      address TEXT,
      area_id TEXT,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS villagers_owner_idx ON villagers(owner_user_id);
  `);
  // area_id may predate this column on an older DB; add it if missing.
  const cols = db.prepare("PRAGMA table_info(villagers)").all();
  if (!cols.some((c) => c.name === "area_id")) {
    db.exec("ALTER TABLE villagers ADD COLUMN area_id TEXT");
  }

  // The chief who owns the citizens. Create the default admin if the DB is brand new.
  let owner = db.prepare("SELECT id FROM users WHERE username = ?").get(OWNER_USERNAME);
  if (!owner) {
    const info = db
      .prepare("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)")
      .run(OWNER_USERNAME, bcrypt.hashSync("admin123", 12), Date.now());
    owner = { id: Number(info.lastInsertRowid) };
    console.log(`Created default user '${OWNER_USERNAME}'.`);
  }

  const counts = apportion(POPULATION_WEIGHTS, TARGET);
  const usedPhones = new Set();
  const now = Date.now();

  const insert = db.prepare(
    `INSERT INTO villagers (owner_user_id, name, phone, address, area_id, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  );

  const seed = db.transaction(() => {
    const removed = db.prepare("DELETE FROM villagers WHERE owner_user_id = ?").run(owner.id).changes;
    let inserted = 0;
    for (const [areaId, count] of counts) {
      const areaName = areaNames.get(areaId);
      for (let i = 0; i < count; i += 1) {
        // Spread created_at over the past ~180 days so the list isn't one timestamp.
        const createdAt = now - between(0, 180 * 24 * 60 * 60 * 1000);
        insert.run(owner.id, makeName(), makePhone(usedPhones), makeAddress(areaName), areaId, createdAt, createdAt);
        inserted += 1;
      }
    }
    return { removed, inserted };
  });

  const { removed, inserted } = seed();

  console.log(`Cleared ${removed} existing citizen(s) for '${OWNER_USERNAME}'.`);
  console.log(`Seeded ${inserted} citizens across ${counts.size} areas.`);
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  console.log("Top areas:");
  for (const [id, count] of top) console.log(`  ${areaNames.get(id)} — ${count}`);

  db.close();
}

main();
