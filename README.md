# Điện Biên Forecast — Cảnh báo thiên tai thông minh cho Điện Biên

> **AI-powered, sub-regional weather and disaster early-warning for Điện Biên** — delivering the right information, to the right people, at the right time, in a form everyone can understand and act on.

> **Product:** Điện Biên Forecast · **Team:** Hination

Điện Biên Forecast transforms raw weather data into **location-specific risk estimates** and **plain-language warnings with concrete actions**.

The system is designed primarily for:

- Commune disaster-prevention officials.
- Village chiefs.
- Local emergency-response teams.

Điện Biên Forecast helps local officials understand danger within seconds, broadcast warnings through existing communication channels, and track which households have received the message or still need support.

The product follows a **communication-first, action-first** principle:

> A warning is not successful when it is published.
> It is successful when the right people receive it, understand it and act before the dangerous event occurs.

---

## 1. The problem

Điện Biên has complex terrain and fast-changing extreme weather, including:

- Dense fog.
- Heavy rain.
- Flash floods.
- Cold spells.
- Winter frost.

These events directly affect agriculture, transport, infrastructure and the lives of highland residents.

Current warning delivery has four major gaps:

| Gap | What it means on the ground |
|---|---|
| **Too coarse** | Provincial forecasts are not always specific enough for districts, commune clusters, valleys, slopes or isolated villages. |
| **Too late** | Information may take too long to reach commune- and village-level residents. |
| **Too abstract** | Technical meteorological figures do not clearly tell residents what they need to do. |
| **Wrong channel or language** | A warning may not reach people through the channels they already use or in a language they easily understand. |

### Goal

Deliver weather information to the:

- Right area.
- Right people.
- Right time.
- Right channel.
- Right language.
- Right action.

A useful warning must answer six questions:

1. **Where** is the danger?
2. **When** may it happen?
3. **What** is the risk?
4. **How serious** is it?
5. **What should people do now?**
6. **How will local officials know whether people are safe?**

---

## 2. Product principle: communication-first, not app-first

Điện Biên Forecast does not require every resident to install or continuously open a weather application.

Many residents cannot reliably depend on a dedicated app because of:

- Weak or intermittent internet access.
- Limited smartphone access.
- Language and literacy barriers.
- Low familiarity with technical weather information.
- The need to receive warnings while working outdoors or away from a screen.

Instead, Điện Biên Forecast equips the people who already coordinate local response:

- **Commune disaster-prevention officials** monitor risks across villages and coordinate resources.
- **Village chiefs** relay warnings locally, track household status and organise direct support.

```text
Weather and risk data
        ↓
Điện Biên Forecast control dashboard
        ↓
Commune official reviews the situation
        ↓
Village chief broadcasts the warning
        ↓
Residents receive and respond
        ↓
Dashboard shows who is safe,
who has not responded
and who needs immediate support
```

Residents do not need mobile data or an installed app.

They may receive warnings through:

- Public loudspeaker.
- Cellular SMS.
- Zalo or community groups.
- Automated calls.
- Direct communication from the village chief.
- Local emergency-response teams.

---

## 3. Primary users

### 3.1 Commune disaster-prevention official

The commune official needs to know:

- Which villages are currently at risk.
- What type of weather hazard is expected.
- When the danger may begin and end.
- Which warnings have been approved and distributed.
- Which villages have acknowledged receipt.
- Which areas have households requesting assistance.
- Where local resources should be prioritised.

### 3.2 Village chief

The village chief needs a real-time control view showing:

- Which households have received the warning.
- Which households have confirmed they are taking action.
- Which households have not responded.
- Which households need assistance.
- Whether roads, bridges or routes are blocked.
- Which household or area must be handled first.

### 3.3 Residents

Residents need warnings that are:

- Short.
- Easy to understand.
- Specific to their location.
- Clear about time and severity.
- Focused on one to three concrete actions.
- Available through channels they already use.

---

## 4. What Điện Biên Forecast delivers

### 4.1 Location-specific 3–7 day forecasts

Điện Biên Forecast generates a 3–7 day forecast for configured locations in Điện Biên using representative coordinates for each area.

Forecast variables may include:

- Temperature.
- Rainfall.
- Rain probability.
- Wind speed.
- Humidity.
- Cloud cover.
- Visibility, where available.

These outputs are location-specific forecast estimates.

They improve local relevance compared with a single provincial forecast but do not replace official forecasts and warnings issued by authorised hydro-meteorological agencies.

The system should not describe coordinate-based API output as an exact official forecast for every household or village.

### 4.2 Automatic warning detection

A deterministic risk engine evaluates weather data against:

- Configurable thresholds.
- Local terrain.
- Historical risk profiles.
- Data-quality confidence.
- Optional trained model scores.

Current MVP risk types:

- Heavy rain.
- Flash-flood risk.
- Dense fog or low visibility.
- Cold and frost risk.

Possible future extensions:

- Landslide risk.
- Severe wind and storms.
- Wildfire risk.

The interface uses a five-level warning scale:

| Level | Meaning | Expected response |
|---|---|---|
| **1 — Safe** | No significant risk | Continue normal activities and monitor updates. |
| **2 — Watch** | Early signs of unfavourable weather | Prepare and follow updates. |
| **3 — Prepare** | Meaningful risk is developing | Protect crops, livestock and vulnerable assets. |
| **4 — Dangerous** | High risk requiring action | Restrict movement and prepare local response. |
| **5 — Emergency** | Immediate or severe danger | Evacuate or follow emergency instructions. |

The prototype warning scale is informed by official disaster-risk guidance.

Điện Biên Forecast is a decision-support prototype and does not issue official government warnings.

### 4.3 Plain-language warnings with concrete actions

The system converts structured risk output into a short bulletin containing:

- Affected location.
- Expected start and end time.
- Warning level.
- Risk type.
- One to three approved actions.
- Instructions for residents.
- Instructions for village or commune officials.

Example:

```text
CẢNH BÁO CAM — MƯA LỚN

Khu vực: Mường Nhé
Thời gian: Từ 18:00 hôm nay đến 06:00 ngày mai

Không đi qua suối hoặc ngầm tràn.
Tránh khu vực gần sườn núi.
Cán bộ bản kiểm tra các hộ có nguy cơ cao.
```

Warnings should not only tell residents to “be careful”.

They must specify:

```text
Where → When → What danger → What action → Action deadline → How to confirm status
```

### 4.4 Multi-channel delivery

The warning engine is designed to support:

- Web dashboard for officials.
- Public loudspeaker.
- SMS.
- Zalo Official Account.
- Community Zalo groups.
- Automated voice calls.
- Loudspeaker-ready text-to-speech output.

Warnings should be targeted to:

- The affected village.
- The affected risk zone.
- Vulnerable households.
- Households near streams.
- Households near steep slopes.
- Elderly people living alone.
- People with mobility limitations.

Warnings should not automatically be sent to every household in the commune unless the whole commune is affected.

### 4.5 Multi-language communication

Current prototype output:

- Vietnamese plain-language bulletins.

Roadmap:

- Thái-language version.
- Mông/Hmong-language version.
- Verified local terminology library.
- Native-speaker review.
- Loudspeaker-ready audio in supported languages.

AI-generated translations must be reviewed before operational use, especially for high-risk warnings.

### 4.6 Radio Studio — one screen from warning to broadcast

The **Radio Studio** (`/radio`, village-chief only) turns an active warning into an actual broadcast without leaving the dashboard.

- **Auto-drafted alert.** The studio reads today's forecast and pre-fills a red alert card and AI risk-summary bullets for the most dangerous communes — dominant disaster, rainfall, peak-hour window and the affected-area band.
- **Message composer.** A 280-character plain-language editor, pre-scoped to the at-risk areas.
- **Area targeting.** Send to selected forecast areas or to every registered villager; the recipient count is computed live from the citizen registry.
- **Multi-channel fan-out.** Loudspeaker, SMS and Zalo. The SMS channel uses the real (stubbed) SMS transport and writes an `sms_logs` row so the map and manage counters stay in sync; loudspeaker and Zalo are simulated at this stage.
- **Voice selection.** Read the alert with an AI text-to-speech voice in **Kinh (Vietnamese)** or **Mông/Hmong**, or with one of the chief's **own recorded clips**. Recordings are captured in-browser via the `MediaRecorder` API, stored in SQLite (8 MB cap), and managed in a rename/delete library with a live `WaveBars` visualiser.
- **Repeat & schedule.** Play the alert 1–5 times with a configurable gap; send now or schedule for later.
- **Drafts & history.** Save a draft for review, or keep a log of everything already broadcast.

### 4.7 Rescue & SOS loop

A two-way citizen ↔ rescuer loop that works even for people who are not in any registry.

- **Citizen SOS screen** (`EmergencyHelp`). One large button captures the caller's location — browser GPS first, server-side IP geolocation as a fallback — plus an optional free-text situation, and posts an **anonymous** help request. On phones this screen replaces the map; on desktop it is reachable from a floating action button.
- **Nearest-first rescue numbers.** The SOS screen lists local emergency contacts sorted by distance to the caller, always backed by the national hotlines (**112 / 115 / 114 / 113**) so the picker is never empty, with tap-to-call.
- **Open contact directory.** Anyone can add a rescue number; a logged-in chief's number is permanent, an anonymous visitor's number auto-expires after **48 hours**.
- **Rescue console** (`/rescue`). Lists help requests from the last 24 hours with the resolved commune name, a **GPS-accurate vs IP-approximate** badge, the reported reason, time-ago and a one-tap Google Maps link. A second tab manages the emergency-number directory. Open help requests also render as live dots on the forecast map (`HelpRequestLayer`).

### 4.8 Seeded citizen registry

`pnpm seed:citizens` populates the chief's contact table with **~10,000 synthetic villager contacts spread across all 45 communes/wards of Điện Biên** in proportion to each unit's real population (urban wards and the Mường Thanh valley dense, remote northern communes sparse). The seed is fixed-PRNG reproducible and idempotent, so the map summary, per-area hover cards, blast dropdown and area-scoped SMS all show and send meaningful numbers on a fresh database — including in production, where `data/` is not committed.

---

## 5. How Điện Biên Forecast works

The complete processing and delivery pipeline is:

```text
DATA SOURCES
├─ Open-Meteo weather forecast
├─ Historical reanalysis data
├─ Terrain and elevation data
├─ Historical disaster records
├─ Local risk configuration
└─ Future local station integration
        ↓
DATA INGESTION AND NORMALISATION
        ↓
LOCATION-SPECIFIC FORECAST PROCESSING
        ↓
RISK ENGINE
├─ Configurable thresholds
├─ Terrain and local risk profile
├─ Optional trained disaster model
├─ Data-quality confidence
└─ Alert cooldown and validation rules
        ↓
STRUCTURED WARNING OUTPUT
├─ Location
├─ Time
├─ Risk type
├─ Warning level
├─ Triggered rules
└─ Approved actions
        ↓
AI COMMUNICATION LAYER
├─ Plain-language Vietnamese
├─ Resident version
├─ Official version
├─ SMS version
├─ Loudspeaker version
└─ Future Thái and Mông/Hmong conversion
        ↓
HUMAN REVIEW
        ↓
DISTRIBUTION
├─ Dashboard
├─ SMS
├─ Zalo
├─ Loudspeaker
└─ Automated call
        ↓
ACKNOWLEDGEMENT AND FIELD FEEDBACK
        ↓
SITUATION CONTROL DASHBOARD
```

---

## 6. Warning decision and AI guardrails

Điện Biên Forecast separates two responsibilities:

```text
Risk decision-making ≠ Language generation
```

### 6.1 Risk engine responsibilities

The risk engine determines:

- Whether a threshold has been exceeded.
- Which area is affected.
- Which risk type is relevant.
- The warning level.
- The expected start and end time.
- Which approved actions are attached to the warning.

The warning level must be traceable to:

- Input weather data.
- Triggered threshold.
- Local risk profile.
- Model score, where used.
- Data timestamp.
- Data-quality status.

### 6.2 AI communication responsibilities

The AI layer may:

- Rewrite structured data into plain language.
- Produce separate versions for residents and officials.
- Shorten content for SMS.
- Format content for Zalo.
- Format content for loudspeaker use.
- Convert approved content into supported languages.

The AI layer must not:

- Increase the warning level.
- Decrease the warning level.
- Change weather figures.
- Change the affected location.
- Change the warning time.
- Invent a disaster type.
- Add unsupported instructions.
- Present uncertain forecasts as certain events.

### 6.3 Supporting news and official notices

Recent news or official notices may be displayed as additional context for officials.

They must not:

- Determine the warning level.
- Block a warning triggered by the risk engine.
- Automatically increase or decrease a warning.
- Replace authorised local reports.
- Replace hydro-meteorological data.

News often appears after an event has already begun, so it must not be required before issuing an early warning.

### 6.4 Recommended approval policy

| Warning level | Default workflow |
|---|---|
| **Level 1–2** | Display on the dashboard. |
| **Level 3** | Generate a draft and notify the operator. |
| **Level 4–5** | Generate a draft, require authorised review and broadcast after approval. |

> **Emergency auto-broadcast:** enable only when an approved operating policy is configured.

---

## 7. Two-way disaster control loop

Điện Biên Forecast is not only a broadcast system.

It creates a feedback loop between:

- Residents.
- Village chiefs.
- Commune officials.
- Local response teams.

```text
Risk detected
        ↓
Warning generated
        ↓
Official reviews and approves
        ↓
Warning broadcast through selected channels
        ↓
Households acknowledge receipt
        ↓
Village chief sees live response status
        ↓
Unresponsive or vulnerable households are prioritised
        ↓
Local teams provide support
        ↓
Field reports return to the commune dashboard
```

A warning is considered successful only when the full chain is completed:

```text
Detect danger → Create warning → Send to the correct area → Residents receive it
→ Residents understand it → Residents take action → Village chief confirms local status
```

---

## 8. Household response

Residents should not need to type long messages.

They may respond using a simple number, button or phone keypad:

- 1 — Đã nhận và đang thực hiện
- 2 — Gia đình cần hỗ trợ
- 3 — Đường bị chia cắt
- 4 — Có người bị thương
- 5 — Thông tin tại đây không đúng

For an automated phone call:

> Nhấn phím 1 nếu gia đình đã nhận cảnh báo và đang thực hiện.  
> Nhấn phím 2 nếu gia đình cần hỗ trợ.  
> Nhấn phím 3 nếu đường đi đã bị chia cắt.

---

## 9. Situation control dashboard

The village chief dashboard should show:

| Metric | Count |
|---|---:|
| Total households in affected area | **86** |
| Received warning | 62 |
| Taking action | 45 |
| Need assistance | 7 |
| No response | 17 |
| Road access blocked | 3 |

The dashboard should create a prioritised task list:

| Household or area | Status | Recommended response |
|---|---|---|
| Elderly person living alone | No response | Assign local team to check. |
| Household near stream | Needs assistance | Support evacuation. |
| Group of riverside homes | High risk | Broadcast again and visit directly. |
| Access road | Blocked | Escalate to commune official. |

The purpose of the dashboard is not to show more weather data.

Its purpose is to help the village chief answer:

> **Who is safe, who has not responded, who needs help and who should be handled first?**

---

## 10. Escalation logic

```text
Send SMS, Zalo and loudspeaker warning
        ↓
Wait for configurable acknowledgement period
        ↓
No acknowledgement
        ↓
Trigger automated call or resend
        ↓
Still no response
        ↓
Assign follow-up task to village chief or response team
        ↓
Escalate unresolved cases to commune level
```

Possible task statuses:

- Not assigned.
- Assigned.
- In progress.
- Household contacted.
- Household safe.
- Assistance required.
- Escalated.
- Completed.

---

## 11. Alert-fatigue controls

To prevent residents from ignoring repeated warnings:

- Alerts are sent only when the level changes or meaningful new information appears.
- Duplicate messages inside a configurable cooldown period are merged.
- Threshold hysteresis prevents repeated switching between levels.
- Each warning includes an expiry time.
- An all-safe or downgrade message is issued when appropriate.
- Low-level warnings are not broadcast through every emergency channel.
- Emergency calls are reserved for high-risk situations.
- Updated warnings should replace previous warnings rather than create unnecessary duplicates.

---

## 12. Current MVP scope

### 12.1 Demo locations

The hackathon demo should show at least three locations in Điện Biên:

- Thành phố Điện Biên Phủ.
- Tuần Giáo.
- Mường Nhé.

The system may include additional configured commune- or ward-level areas.

Do not describe every configured point as an exact official commune forecast.

> **Use:** “Location-specific forecast estimate.”  
> **Avoid:** “Official commune-level forecast.”

### 12.2 MVP flow

```text
Select location
        ↓
Fetch 3–7 day forecast
        ↓
Normalise weather data
        ↓
Evaluate risk thresholds
        ↓
Assign warning level
        ↓
Generate structured warning
        ↓
Create plain-language bulletin
        ↓
Review and approve
        ↓
Simulate or execute multi-channel delivery
        ↓
Track acknowledgement and support requests
```

### 12.3 Capability status

| Capability | Status |
|---|---|
| Weather forecast API integration | Implemented |
| 3–7 day location-specific forecast | Implemented |
| Configurable warning thresholds | Implemented |
| Interactive risk map | Implemented |
| Plain-language Vietnamese bulletin | Implemented |
| Villager or household registry | Implemented (≈10k seeded contacts across 45 communes) |
| Radio Studio broadcast composer | Implemented |
| Voice recording + Kinh/Hmong TTS voices | Implemented |
| Citizen SOS + rescue console | Implemented (live help-request loop) |
| Emergency-number directory | Implemented |
| SMS interface | Simulated or adapter-ready |
| Live SMS gateway | Roadmap unless a provider is configured |
| Zalo Official Account integration | Roadmap (adapter simulated) |
| Loudspeaker or TTS delivery | Composition implemented; physical delivery simulated |
| Thái-language conversion | Roadmap |
| Household acknowledgement loop | MVP target or simulated flow |
| Live field-response tracking | SOS requests live; broader tracking on roadmap |
| Direct local station feed | Roadmap |

Update this table according to the features that are actually working in the repository.

Do not describe simulated integrations as fully operational.

---

## 13. Engineering architecture

### 13.1 Data sources

Potential sources include:

- Open-Meteo for weather forecasts.
- GFS forecast data provided through Open-Meteo.
- ERA5 reanalysis estimates for historical weather context.
- NASADEM or SRTM for elevation and terrain-related features.
- Historical disaster records with sufficient location and date quality.
- Local risk-zone configuration.
- Future integration with the Điện Biên Hydro-Meteorological Station.

Pre-trained hazard signals (independent of the self-trained model):

- **Flash flood** — NOAA GloFAS v4 river-discharge forecasts via the free Open-Meteo Flood API. Each commune's forecast discharge is scored against its own 30-year discharge climatology (percentiles), so the level reflects local abnormality, not raw flow. Build the one-time per-commune climatology cache with `python -m model.hazard_providers --build-climatology` (writes `data/flood_climatology.json`; re-run any time to fill gaps).
- **Landslide (sạt lở)** — NASA LHASA nowcast probability, queried live from the NASA Earthdata ArcGIS ImageServer (`gis.earthdata.nasa.gov`) for today and tomorrow. Both fetches are best-effort: a rate-limited or unavailable source is skipped without lowering any level or crashing the refresh.

ERA5 is reanalysis data, not direct station observation.

Local forecasts based on representative coordinates should not be described as exact official forecasts for every household or village.

### 13.2 Forecast processing

The system may use approximately 30 days of historical reanalysis estimates before the future forecast period to complete rolling rainfall or weather-history features.

```text
Historical reanalysis context
        +
Future weather forecast
        ↓
Complete rolling features
        ↓
Risk model and rule engine
```

If historical data is unavailable, the service should:

- Fall back gracefully.
- Mark reduced confidence.
- Avoid silently presenting incomplete data as equally reliable.
- Continue serving cached data where appropriate.

### 13.3 Risk engine

The risk engine may combine:

- Deterministic weather thresholds.
- Terrain features.
- Historical risk profile.
- Optional trained model score.
- Pre-trained GloFAS flood level and NASA LHASA landslide level.
- Data-quality confidence.

The warning level for each commune-hour is the most alarming of the trained-model/heuristic level, the GloFAS flood level, and the LHASA landslide level (`level = max(...)`). The winning signal sets the dominant disaster type. A missing external signal never lowers a level, and each hour records its `external` flood/landslide inputs so the decision stays auditable.

The final warning level must remain auditable.

The system should retain:

- Input values.
- Triggered rules.
- Model score, where used.
- Data source.
- Data timestamp.
- Warning level.
- Warning creator.
- Approving official.
- Delivery channels.
- Delivery status.
- Household acknowledgements.

---

## 14. Model evaluation

Any model-performance claim must be linked to a reproducible evaluation report.

Recommended document: [`docs/model-evaluation.md`](docs/model-evaluation.md)

The report should include:

- Dataset period.
- Number of samples.
- Number of positive disaster events.
- Class distribution.
- Train, validation and test split strategy.
- Time-based or event-based holdout method.
- Precision.
- Recall.
- F1-score.
- ROC-AUC.
- Confusion matrix.
- Performance by disaster type.
- Threshold-selection method.
- Known limitations.

Accuracy alone should not be used as the main metric for an imbalanced disaster-detection problem.

Avoid presenting model accuracy as a production guarantee.

---

## 15. Tech stack

### 15.1 Backend — forecast API and risk pipeline (`hination/`)

| Layer | Technology | Role |
|---|---|---|
| **Forecast API** | Python 3.10+ · FastAPI ≥ 0.100 · Uvicorn · Pydantic 2 | Serves forecast, risk and warning data; downscales the per-day model output to per-hour danger for the timeline scrubber. |
| **Risk model** | PyTorch ≥ 2.2 multi-task NN (`models/disaster_nn.pt`) · NumPy | Auditable per-commune risk scores. The `StandardScaler` mean/scale are baked into the checkpoint, so inference needs only torch + numpy. |
| **Pre-trained hazards** | NOAA GloFAS v4 (via Open-Meteo Flood API) · NASA LHASA nowcast | Flood discharge scored against per-commune 30-year climatology; landslide probability queried live. `level = max(model, flood, landslide)`. |
| **Data ingestion** | `requests` HTTP client with cache and graceful fallback · Google Earth Engine (`earthengine-api`) | Fetches Open-Meteo forecasts, ERA5/GFS reanalysis context and terrain features. |
| **Scheduler** | `schedule` | Hourly forecast refresh and risk recompute (`run_hourly_scheduler.sh`). |
| **Training (offline)** | scikit-learn ≥ 1.4 · pandas ≥ 2.0 | `StandardScaler`, metrics and feature frames — needed only on the box that (re)trains, not to serve predictions. |

### 15.2 Frontend — dashboard, Radio Studio and Rescue console (`hination-fe/`)

| Layer | Technology | Role |
|---|---|---|
| **Framework** | Next.js 16 (App Router · React Server Components · Server Actions) · React 19 · TypeScript 5.9 | Server-rendered dashboard; mutations run as server actions, no separate API layer for the app's own writes. |
| **Styling** | Tailwind CSS 4 (`@tailwindcss/postcss`) | Utility-first styling across map, studio and console. |
| **Map** | Leaflet 1.9 · react-leaflet 5 | Interactive risk map, per-area hover cards, timeline scrubber and live help-request dots. |
| **Icons** | `@phosphor-icons/react` 2 | Consistent icon set. |
| **Storage** | better-sqlite3 12 (Node.js runtime) · bcryptjs | Villager registry, broadcasts, voice recordings, emergency contacts, help requests and SMS log; hashed chief login. |
| **Audio** | Browser `MediaRecorder` API → SQLite blob · `WaveBars` visualiser · Kinh/Hmong TTS clips | In-browser voice capture and playback for the Radio Studio. |
| **Geolocation** | Browser Geolocation API · server-side IP geolocation fallback | Locates SOS callers and sorts rescue numbers nearest-first. |
| **Testing** | Vitest 4 · Testing Library · jsdom | Component and unit tests. |
| **Tooling** | pnpm 11 · ESLint 9 (`eslint-config-next`) | Package management and linting. |

### 15.3 AI communication & delivery

| Layer | Technology | Role |
|---|---|---|
| **AI communication** | OpenAI-compatible LLM | Generates controlled plain-language bulletin formats and the studio's risk-summary bullets. |
| **Delivery** | SMS (real stub + log) · Zalo and loudspeaker adapters (simulated) | Multi-channel fan-out from the Radio Studio. |
| **Deployment** | Docker Compose · Nginx | Runs frontend, backend and the optional scheduler behind a reverse proxy. |

---

## 16. Privacy, security and access control

The household registry may contain personal or sensitive information.

The hackathon demo should use synthetic household data.

Operational deployment requires:

- Approved data-sharing procedures.
- Consent procedures where required.
- Role-based access control.
- Commune officials limited to authorised areas.
- Village chiefs limited to assigned villages.
- Audit logging for warning creation, approval and delivery.
- Encryption of phone numbers.
- Protection of sensitive household attributes.
- Defined data-retention periods.
- Secure backup and recovery.
- Incident-response procedures.

Sensitive attributes may include:

- Phone number.
- Home location.
- Disability or mobility limitation.
- Elderly person living alone.
- High-risk household classification.
- Evacuation status.
- Support-request status.

These data should only be collected when operationally necessary.

---

## 17. Meeting the minimum submission requirements

| Requirement | Điện Biên Forecast demonstration |
|---|---|
| **3–7 day forecast for at least 3 locations** | Location-specific forecast for Điện Biên Phủ, Tuần Giáo and Mường Nhé. |
| **Automatic warning on threshold breach** | Deterministic risk engine creates a warning candidate when configured thresholds are exceeded. |
| **Simple interface for non-experts** | Color, icon, location, time and one-to-three concrete actions. |
| **Resident-understandable output** | Short SMS, warning card or loudspeaker-ready bulletin. |
| **Architecture document** | This README and detailed architecture documentation. |
| **One-page deck** | Link to the final one-page solution deck. |
| **Source data** | Documented in the data-source and architecture sections. |
| **Processing model** | Forecast processing, risk engine and AI communication layer. |
| **Distribution channels** | Dashboard, SMS, Zalo, loudspeaker and automated-call adapters. |
| **Deployment roadmap** | MVP, pilot and scale phases. |

Recommended project links:

- [One-page solution deck](docs/HINATION-one-page-deck.pdf)
- [System architecture](docs/architecture.md)
- [Model evaluation](docs/model-evaluation.md)
- [Demo script](docs/demo-script.md)

---

## 18. Demo scenario

### 18.1 Scenario

A highland area in Mường Nhé is forecast to receive heavy rainfall.

The affected village contains households near streams and steep slopes.

### 18.2 Demo flow

1. Open the control dashboard.
2. Compare Điện Biên Phủ, Tuần Giáo and Mường Nhé.
3. Show Mường Nhé moving to a high warning level.
4. Open the warning details:
   - Triggered threshold.
   - Forecast time.
   - Affected location.
   - Risk type.
5. Generate a resident bulletin.
6. Generate a village-chief bulletin.
7. Show the SMS version.
8. Show the loudspeaker version.
9. Approve and press Broadcast warning.
10. Display household response status:
    - Received.
    - Taking action.
    - Needs assistance.
    - No response.
11. Assign a follow-up task to a local response team.
12. Escalate unresolved cases to the commune official.

### 18.3 Demo message

```text
CẢNH BÁO NGUY HIỂM — MƯA LỚN

Từ 18:00 hôm nay đến 06:00 ngày mai,
khu vực Mường Nhé có nguy cơ mưa lớn.

Không đi qua suối hoặc ngầm tràn.
Tránh khu vực gần sườn núi.
Các hộ cần hỗ trợ trả lời số 2.
```

---

## 19. Running the demo

### 19.1 Full stack

```bash
docker compose up --build -d

# nginx:   http://localhost
# frontend: http://localhost:1111
# backend:  http://localhost:1112

# Optional scheduler
docker compose --profile scheduler up --build -d
```

### 19.2 Backend only

```bash
cd hination
python -m venv .venv

# Linux or macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

API documentation: `http://localhost:8000/docs`

### 19.3 Frontend only

```bash
cd hination-fe
pnpm install

# Seed ~10k synthetic villager contacts across the 45 communes (idempotent).
# Required on a fresh DB so the map summary, hover cards, blast dropdown and
# area-scoped SMS have data to show — including in production, where data/ is gitignored.
pnpm seed:citizens

pnpm dev
```

Frontend development URL: `http://localhost:3000`

Key frontend routes:

- `/app` — public forecast map (mobile shows the citizen SOS screen).
- `/manage` — village-chief villager registry and SMS (login required).
- `/radio` — Radio Studio broadcast composer (login required).
- `/rescue` — rescue console and emergency-number directory (open to all).

For complete engineering details, see:

[hination/README.md](hination/README.md)

---

## 20. Deployment roadmap

### 20.1 Phase 1 — Hackathon MVP

- 3–7 day forecast for at least three locations.
- Automatic threshold-based warning candidates.
- Interactive official-facing map.
- Plain-language Vietnamese bulletin.
- Simulated SMS and loudspeaker output.
- Demo household registry.
- Simulated acknowledgement dashboard.

### 20.2 Phase 2 — Local pilot

- Validate thresholds with hydro-meteorological experts.
- Connect a live SMS gateway.
- Integrate Zalo Official Account.
- Generate loudspeaker-ready TTS audio.
- Verify Thái and Mông/Hmong warning templates with native speakers.
- Pilot with selected communes and villages.
- Add real acknowledgement tracking.
- Add real support-request tracking.
- Define official approval and escalation procedures.

### 20.3 Phase 3 — Operational scale

- Direct integration with local station feeds.
- Calibrated terrain and local risk profiles.
- Expansion to more commune- and village-level areas.
- Automated calls for high-risk households.
- Integration with local emergency-response teams.
- Offline and degraded-network operating modes.
- Audit and reporting tools.
- Post-event analysis.
- Expansion to neighbouring north-western provinces where appropriate.

---

## 21. Repository layout

| Path | Contents |
|---|---|
| [`hination/`](hination/) | Python backend, forecast API, risk engine, data pipelines and scheduler. |
| [`hination-fe/`](hination-fe/) | Next.js frontend, interactive map, warning control, household management and response management. |
| [`nginx/`](nginx/) | Reverse-proxy configuration. |
| [`data/`](data/) | Runtime weather, terrain and disaster-data caches. |
| [`docs/`](docs/) | Architecture, model evaluation, demo script and one-page deck. |
| [`docker-compose.yml`](docker-compose.yml) | One-command local deployment. |
| [`CONTEXT.md`](CONTEXT.md) | Domain glossary, geography, warning levels and risk types. |

---

## 22. North-star metric

Điện Biên Forecast should not be evaluated only by weather-model accuracy.

The north-star metric is:

> **The percentage of households in the affected risk area that receive, understand and confirm the required action before the dangerous event begins.**

Supporting metrics:

- Time from risk detection to warning broadcast.
- Percentage of affected households reached.
- Acknowledgement rate within five minutes.
- Number of households requiring support.
- Number of households with no response.
- Time required to resolve a support request.
- False-warning rate.
- Percentage of warnings delivered before the event.
- Percentage of residents who correctly understand the required action.
- Percentage of village chiefs who confirm local status.

---

## 23. Product positioning

Điện Biên Forecast is not simply:

> A weather forecast application for Điện Biên.

Điện Biên Forecast is:

> **An AI-assisted last-mile disaster-warning and local response-control system** that transforms weather data into clear actions, distributes them through existing community channels, and helps local officials track who is safe and who still needs support.

> **Right place. Right time. Right language. Right action.**  
> **Đúng khu vực — Đúng thời điểm — Đúng ngôn ngữ — Đúng hành động.**

Built by **Team Hination** for the Điện Biên disaster-prevention challenge — turning weather information into timely, understandable and trackable community action.