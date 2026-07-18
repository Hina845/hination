# HINATION — Cảnh báo thiên tai thông minh cho Điện Biên

> **AI-powered, sub-regional weather & disaster early-warning for Điện Biên province** — delivering the right information, to the right people, at the right time, in a form everyone can understand.

HINATION turns raw weather data into **commune-level risk forecasts** and **plain-language warnings with concrete actions**, presented on a color-coded map built for the **village chief / commune official** — who reads the danger in seconds and broadcasts it to residents by **loudspeaker and SMS**, reaching everyone even where the internet doesn't.

---

## 1. The problem

Điện Biên has complex terrain and fast-changing, extreme weather — dense fog, sudden floods, flash floods, and winter frost — that seriously affect agriculture, transport, and the lives of highland residents.

Today, forecast information has four gaps:

| Gap | What it means on the ground |
|---|---|
| **Too coarse** | Forecasts exist only at the **provincial** level — not specific enough for a district or a cluster of communes, especially in disaster-prone valleys and slopes. |
| **Too late** | Commune- and village-level residents receive warnings late, after the risk has already grown. |
| **Too abstract** | Information is presented as technical text — hard to act on for people who don't read meteorological bulletins. |
| **Wrong channel / language** | It doesn't reach people where they are (Zalo, SMS, loudspeaker) or in the language they speak (Thái, Mông/Hmong). |

**Goal:** build an AI solution that delivers weather information to the **right people, at the right time, in the right language** — with early warnings that tell residents and village officials exactly what to do.

---

## 2. The key insight: the last mile

The hardest part of disaster warning in the highlands is **not the forecast — it's getting it to people who will act on it.** Điện Biên's reality forces this to the front:

- **Residents don't (and won't) use a forecast app.** Most highland villagers won't install, learn, or open a dashboard — many aren't comfortable with smartphones or don't read technical text. Building "an app for residents" quietly assumes an audience that isn't there.
- **The internet often isn't there either.** In mountainous communes, connectivity is intermittent or absent. A warning that requires every resident to be online, right now, will not arrive.

**So HINATION does not try to push a dashboard onto residents. It equips the person who is already trusted to warn the village — the village chief / commune official — and lets them relay.**

```
   HINATION dashboard              The relay (village chief)            The village
 ┌───────────────────────┐      ┌───────────────────────────┐      ┌────────────────────┐
 │ Map + color danger     │      │ Reads the situation in     │      │ Loudspeaker         │
 │ scale + "what to do"   │─────►│ seconds, decides, acts:    │─────►│ announcement        │
 │ + one-click SMS        │      │  • public loudspeaker      │      │ (reaches everyone,  │
 │                        │      │  • emergency SMS blast     │      │  no phone needed)   │
 │ (one connected device, │      │  • door-to-door / Zalo     │      │ SMS to households   │
 │  the chief's)          │      │                            │      │ → villagers prepare │
 └───────────────────────┘      └───────────────────────────┘      └────────────────────┘
```

**Why this works:**

- **Only one device needs connectivity** — the chief's. The village doesn't need the internet; the **loudspeaker reaches everyone, including people with no phone at all.**
- **The chief is a fast decision-maker, not a data analyst.** The dashboard is tuned for a 5-second read (color + icon + one action line), so the chief can *immediately* fire a loudspeaker announcement or an SMS blast about the upcoming disaster and let every household prepare.
- **It uses trust that already exists.** People act on their chief's word — a channel far stronger than a notification from an unfamiliar app.

This "**dashboard for the chief → broadcast to the village**" model is the design decision that makes every other feature useful.

---

## 3. What HINATION delivers

Mapped directly to the required outcomes:

### ✅ Sub-regional detailed forecasts
Instead of one provincial number, HINATION produces a **7-day, hour-by-hour forecast for each of the 45 communes** of Điện Biên (post-2025 administrative merger) — including the disaster-prone highland areas. Each area gets its own weather series (temperature, rain, wind, humidity, cloud cover) driven by its own coordinates and terrain profile.

### ✅ Early warnings with concrete actions
When a dangerous-weather threshold is exceeded (heavy rain, frost, flash flood, storm), the system **automatically raises an alert** and generates a **short, plain-language bulletin telling residents and officials what to do** — not just a risk number. Alerts follow Vietnam's national standard (**Quyết định 18/2021/QĐ-TTg**) and a simple **5-level danger scale**.

### ✅ Multi-channel & multilingual — built for the relay
The chief turns one on-screen warning into a village-wide broadcast:
- **Villager registry + one-click emergency SMS** to every household in the commune (built into the Manage screen).
- Architecture is channel-agnostic — **public loudspeaker, SMS and Zalo** plug into the same warning engine, so the message reaches people **whether or not they have a phone or the internet.**
- Bulletins are generated in **Vietnamese** today, with **local-language conversion (Thái, Mông/Hmong)** on the roadmap for ethnic-minority areas.

### ✅ Intuitive interface — a 5-second read for the village chief
The dashboard is designed for the **commune official / village chief**, not for individual residents. The main screen is an **interactive map, not a table of numbers**: each commune is a colored dot on a **green → red danger scale**, with **icons for the disaster type** (flood, landslide, storm, wildfire, strong wind) and a short "việc cần làm" (what to do) line. The chief grasps the situation at a glance and can act — loudspeaker or SMS — within seconds, no meteorological training required.

---

## 4. The idea / how it works

HINATION combines a **physics- and data-driven risk model** with an **AI news layer**, then presents the result visually.

```
  DATA SOURCES                MODEL LAYER                 DELIVERY
 ┌───────────────┐        ┌──────────────────┐       ┌────────────────────┐
 │ Open-Meteo GFS│──────► │ 7-day hourly      │       │ Interactive map     │
 │  (forecast)   │        │ forecast per      │──────►│ (color + icons)     │
 │ ERA5 archive  │──────► │ commune           │       │                     │
 │  (climate)    │        │                   │       │ Plain-language      │
 │ NASADEM/SRTM  │──────► │ Trained PyTorch   │──────►│ warning bulletins   │
 │  (terrain)    │        │ disaster model +  │       │                     │
 │ IBTrACS/GLC/  │──────► │ heuristic rules   │       │ Emergency SMS to    │
 │  VDDMA (past) │        │ → risk 0–1,       │──────►│ registered villagers│
 └───────────────┘        │   alert level 1–5 │       │                     │
        ▲                 └──────────────────┘        │ (Zalo / loudspeaker │
        │                          ▲                   │  ready)             │
  Brave news search  ─────────────►│  AI brief         └────────────────────┘
  + LLM summariser   (grounded, per-area "what to do") 
```

**Two independent risk signals, combined for robustness:**

1. **Model risk (0–1 → alert level 1–5).** A trained neural network plus terrain- and rainfall-aware heuristic rules score each commune/hour for flood, landslide, storm and wildfire risk against VNDMS thresholds (e.g. rain 24h: 50 / 100 / 200 mm).
2. **AI news signal (0–2).** For each area, the system searches recent Vietnamese news (VTV, local press, the Hydro-Meteorological Station, government notices), and an LLM summarises **only** the relevant, grounded items into a short "what to do" bulletin — never inventing figures.

The two are merged into a single **overall danger level** shown on the map, so the warning reflects both the numerical model and the latest on-the-ground reporting.

### Engineering highlights — the hard problems

- **Antecedent seeding (bridging past + future).** The trained network relies on 7/14/30-day rolling-rainfall windows, but a live GFS forecast only contains *future* data — leaving those windows empty and biasing every prediction toward "no disaster." HINATION solves this by **fetching the ~30 days of observed daily weather from the ERA5 archive and stitching it in front of the GFS forecast series**, so the rolling features are complete on the very first forecast hour. Seeding is best-effort with a forecast-only fallback (`model/antecedent.py`).
- **Training labels grounded in real events.** Historical weather days are labeled by **matching against real disaster records** (IBTrACS typhoons, NASA Global Landslide Catalog, VDDMA floods/storms) by date and location — so the model learns from what actually happened, not just from rainfall thresholds.
- **Credible alerts via two-signal fusion.** The raw model tends to over-warn, so its level is deliberately **reduced by one and combined with the independent, news-grounded AI signal (0–2)**. Reaching the top of the scale requires corroboration from real-world reporting — cutting false alarms while keeping genuine emergencies loud.
- **Resilient data access.** Vietnamese networks frequently block the upstream weather/DNS hosts, so the ingestion layer uses a **multi-endpoint client with circuit-breaker, DNS fallback, and stale-cache serving** — the forecast keeps working even when a data source is unreachable.

---

## 5. Tech stack

| Layer | Technology | Role |
|---|---|---|
| **Forecast API** | Python · **FastAPI** · Uvicorn | Serves combined 7-day × 45-area forecast; ETag caching, health checks, graceful stale-data fallback. |
| **Disaster model** | **PyTorch** multi-task neural net (`disaster_nn.pt`) + scikit-learn / heuristic rules | Predicts disaster probability, type, and severity level from weather + terrain + history. |
| **Data ingestion** | `requests` + resilient multi-endpoint HTTP client | Open-Meteo (GFS forecast & ERA5 archive), NASADEM/Open-Elevation terrain, with circuit-breaker + disk cache for unreliable networks. |
| **Scheduler** | `schedule` | Hourly refresh: re-fetch forecast → recompute risk → publish new snapshot. |
| **Frontend** | **Next.js 16** · **React 19** · TypeScript · **Leaflet** map · Tailwind CSS · Phosphor icons | Color-coded commune map, timeline, danger legend, villager management, emergency-SMS flow. |
| **AI brief** | LLM (OpenAI-compatible) + **Brave news search** | Grounded, per-area "what to do" bulletins in Vietnamese. |
| **Storage** | SQLite (`better-sqlite3`) | Villager registry (per commune) + shared AI-brief cache. |
| **Delivery** | SMS module (villager registry) · Zalo / loudspeaker-ready architecture | Push warnings to residents and officials. |
| **Deployment** | **Docker Compose** · Nginx reverse proxy | One-command stack: nginx (:80) → frontend (:1111) → backend (:1112) + optional scheduler. |

### Data sources
NOAA **GFS** (13 km forecast, via Open-Meteo) · **ERA5** reanalysis climate baseline (2015–present) · **NASADEM/SRTM** terrain (elevation, slope, aspect) · historical disaster catalogs from **IBTrACS** (typhoons), **NASA GLC** (landslides) and **VDDMA** (Vietnam floods/storms). All free / open, plus room to integrate the Điện Biên Hydro-Meteorological Station feed.

### Model quality (held-out test set)
The trained disaster network reaches **AUC ≈ 0.82** on disaster detection, with **~93–95% accuracy** on disaster-type and severity classification. Terrain confidence is factored in: landslide risk is discounted for communes without a calibrated terrain profile, avoiding false alarms.

---

## 6. Meeting the minimum submission requirements

| Requirement | Where it's demonstrated |
|---|---|
| **3–7 day forecast for ≥3 locations** | 7-day hourly forecast for **all 45 communes** (well beyond 3), served at `GET /api/v1/forecasts/latest` and rendered on the map. |
| **Automatic warning on threshold breach** | Risk engine raises **alert levels 1–5** per VNDMS QĐ 18/2021 thresholds and auto-generates a bulletin the moment a threshold is crossed. |
| **Simple interface for non-experts** | Chief-facing map with **color scale + disaster icons + plain "what to do" text** (danger legend An toàn → Rất cao), designed as a 5-second read that drives an immediate loudspeaker/SMS broadcast to residents. |
| **Architecture doc** | This README + the detailed engineering guide in [`hination/README.md`](hination/README.md) and domain glossary in [`CONTEXT.md`](CONTEXT.md). |

---

## 7. Running the demo

**Full stack (recommended):**
```bash
docker compose up --build -d
# nginx → http://localhost   |   frontend :1111   |   backend :1112
# Optional hourly refresher:
docker compose --profile scheduler up --build -d
```

**Backend only (development):**
```bash
cd hination
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000           # docs at /docs
```

**Frontend only (development):**
```bash
cd hination-fe
pnpm install
pnpm dev                                             # http://localhost:3000
```

See [`hination/README.md`](hination/README.md) for the full engineering reference (modules, API schema, training, configuration).

---

## 8. Deployment roadmap

- **Now:** 45-commune 7-day forecast · 5-level auto-warnings · interactive map · AI bulletins · villager SMS registry · Dockerized stack.
- **Next:** wire a live SMS gateway + **Zalo Official Account**; **loudspeaker/TTS** audio bulletins; **Thái & Mông/Hmong** translation of warnings.
- **Later:** direct integration with the Điện Biên Hydro-Meteorological Station feed; push notifications; expansion to neighbouring Tây Bắc provinces.

---

## 9. Repository layout

```
hination/          Python backend — forecast API, disaster model, data pipelines, scheduler
hination-fe/       Next.js frontend — map UI, danger scale, villager & SMS management
nginx/             Reverse-proxy config for the production stack
data/              Cached weather/terrain/disaster data (built at runtime)
docker-compose.yml One-command production stack
CONTEXT.md         Domain glossary (geography, disaster types, alert standards)
```

---

*Built for the Điện Biên disaster-prevention challenge — bringing timely, understandable, actionable weather warnings to every commune.*
