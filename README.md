# NutriAI — Not a calorie counter. A nutrition safety net.

> India does not have a calorie problem. It has a micronutrient and metabolic
> problem — and it eats from a shared pot, on a budget, in twenty languages.
> We built for that.

**Smart India Hackathon 2026 · PS SIH26198 · MedTech / HealthTech · Team ISOLATE**

NutriAI is a multi-agent nutrition assistant built on **Indian food composition
data** (IFCT 2017, ICMR), not American. It models how much iron you actually
*absorb* rather than just eat, splits one family dish across every member
against their own ICMR requirement, finds the cheapest way to close a nutrient
gap, screens every recommendation for drug–food interactions, and can phone you
in Hindi to log a meal.

**The rule the whole system rests on: the language model never produces a
nutrient number.** The vision agent names ingredients and estimates grams.
Every calorie and milligram comes from a composition-table lookup, and every
response carries the `source` it came from.

---

## Table of contents

- [Run it in 5 minutes](#run-it-in-5-minutes)
- [Verify it works](#verify-it-works)
- [Troubleshooting](#troubleshooting)
- [What it does](#what-it-does)
- [Data sources](#data-sources)
- [Architecture](#architecture)
- [API reference](#api-reference)
- [Voice agent setup (optional)](#voice-agent-setup-optional)
- [Environment variables](#environment-variables)
- [Known limitations](#known-limitations)
- [Tests](#tests)
- [Attribution](#attribution)

---

## Run it in 5 minutes

### Prerequisites

| | Version used in development | Notes |
|---|---|---|
| **Python** | 3.13.7 | 3.11+ works |
| **Node** | 24.11.0 | 18+ works |
| **OpenAI API key** | — | required; [get one](https://platform.openai.com/api-keys) |
| Database | — | **none needed** — SQLite is the default |

You do **not** need Docker, Postgres, Redis, or a Sarvam account to run the app.

### 1. Clone

```bash
git clone https://github.com/Harsh-Go-yal/NutriAI.git
cd NutriAI
```

### 2. Backend

```bash
cd backend
python -m venv .venv
```

Activate it — **this differs by shell**:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Windows Git Bash
source .venv/Scripts/activate
# macOS / Linux
source .venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
```

Create your config:

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

Open `backend/.env` and set **one** value:

```env
OPENAI_API_KEY=sk-proj-your-key-here
```

Everything else can stay at its default. Start the server:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8020 --reload
```

You should see `Application startup complete.` The database file
`nutrition_ai.db` is created automatically on first run.

- API → <http://localhost:8020>
- Interactive docs → <http://localhost:8020/docs>

### 3. Frontend

In a **second terminal**:

```bash
cd frontend
npm install

# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

`frontend/.env` already points at the backend:

```env
VITE_API_BASE_URL=http://localhost:8020/api/v1
```

Start it:

```bash
npm run dev
```

### 4. Open the app

**<http://localhost:5173/chat>**

> **Port note:** the backend runs on **8020**, not 8000. Port 8000 is commonly
> taken by other local services. If you change it, update
> `frontend/.env` to match or the UI will not reach the API.

---

## Verify it works

Confirm the backend is healthy:

```bash
curl http://localhost:8020/api/v1/health
```

Expected — `llm_api_status: "ok"` means your OpenAI key is valid and reachable:

```json
{"status":"ok","timestamp":1789930677.5,"llm_api_status":"ok"}
```

Then try these in the chat UI, in order. This is the demo path, and each one
exercises a different layer:

| # | Type this | What should happen |
|---|---|---|
| 1 | `How much protein is in 150 g paneer?` | **28.29 g**, with `Paneer · IFCT 2017` listed under SOURCES |
| 2 | `I had 2 roti and a katori of dal for lunch` | Logs it, prints today's running total, the sidebar calendar turns green |
| 3 | `how much iron did I absorb if I had chai with it` | **~10 mg on the plate → ~0.3 mg absorbed.** The absorption insight |
| 4 | `close my gaps under 200 rupees` | A ₹-costed basket, solved by `scipy linprog (HiGHS)` |
| 5 | `make me a meal plan` | A 7-day plan, saved to **My Plan** |
| 6 | `what is my meal plan for today` | Reads the *saved* plan back (does not regenerate it) |
| 7 | Click a green square in **Log history** | Full-day view: macros, meals by slot, micronutrients, per-item sources |
| 8 | Click the 🖼 icon, attach a meal photo | Ingredients + measured nutrients |

If step 1 returns a number **without** a source line, something is wrong —
every nutrient claim in this app is supposed to be attributed.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `llm_api_status: "invalid_key_or_error"` | Bad or missing `OPENAI_API_KEY` | Check `backend/.env`; restart the server (it reads `.env` only at startup) |
| `llm_api_status: "no_key"` | `.env` not created | `cp .env.example .env` in `backend/` |
| Chat shows "Could not load agents" | Frontend cannot reach the backend | Is the backend up on 8020? Does `frontend/.env` match that port? |
| `ModuleNotFoundError: No module named 'openai'` | venv not activated, or deps not installed | Activate the venv, re-run `pip install -r requirements.txt` |
| `[Errno 10048] error while attempting to bind` (Windows) | Port 8020 already in use | Kill the old process, or use another port and update `frontend/.env` |
| Vite starts but the page is blank | Stale dependency cache | `rm -rf node_modules/.vite && npm run dev` |
| Changed `.env` but nothing happened | Settings load once at startup | Restart the backend |
| `psycopg2` fails to build | Only needed for Postgres | Ignore it on SQLite, or drop that line from `requirements.txt` |
| A food returns amber "estimate" | It is in neither IFCT nor USDA | Working as designed — the app flags unmeasured values rather than hiding them |

### Docker alternative (Postgres + Redis)

```bash
cp backend/.env.example backend/.env   # set OPENAI_API_KEY
docker compose up --build
```

Backend on `:8000`, frontend on `:5173`. No credential has a default in
`docker-compose.yml` — a missing key fails loudly rather than silently using
someone else's.

---

## What it does

| Feature | Why it is different |
|---|---|
| **Hidden-hunger detector** | 19 micronutrients from IFCT 2017 judged against ICMR-NIN RDA 2020 — plus an **absorption model**: tea with a meal cuts non-heme iron uptake ~60%, vitamin C triples it, calcium competes, phytates suppress. The app says *"move your chai 90 minutes"*, not *"eat more iron"*. |
| **Household mode** | One thali photo → split across every family member → four different verdicts on one pot → one cooking session with per-person tweaks. |
| **Nutrition-per-rupee optimiser** | A linear program (`scipy`/HiGHS) closing nutrient gaps at minimum cost. Not an LLM — reproducible, millisecond-fast. |
| **Honest Indian food vision** | Photo models fail on sambar and biryani because calories hide in invisible oil. We classify, then ask two questions (home/restaurant, oil level) and apply a cooking-method multiplier over IFCT. |
| **Clinical safety layer** | Deterministic rules: warfarin↔vitamin K, metformin↔B12, levothyroxine↔calcium, ACE-inhibitors↔potassium; CKD/gout/pregnancy/hypertension guardrails; hard refusal + dietitian escalation. Every finding cites its basis. |
| **Voice check-ins** | Scheduled outbound calls in Hindi/Marathi/Tamil via Sarvam. Opt-in **per meal slot**, explicit consent required, enforced quiet hours 21:30–07:00. |
| **Chat front door** | One assistant routes to every capability — the user never needs to know which agent owns a feature. Sessions, plans, logs and agent runs are all persisted. |
| **Habit streaks** | XP, levels, streak shields, squads. Database-backed, so a restart never resets a streak. |

## Data sources

Consulted strictly in this order:

1. **IFCT 2017** — Indian Food Composition Tables, National Institute of
   Nutrition (ICMR), Hyderabad. **542 foods**, lab-measured across six regions:
   macros, **19 micronutrients**, **18 amino acids**, regional names in 12
   languages, vegetarian tags. Shipped as `backend/app/data/ifct2017.json`.
2. **USDA FoodData Central** — prepared dishes and non-Indian foods IFCT lacks.
3. **OpenAI estimate** — last resort only, **flagged in the API response and
   shown amber in the UI**. Never passes as measured data.

Requirements: **ICMR-NIN RDA 2020** (note: iron for an adult Indian woman is
**29 mg**, far above Western figures, precisely because of the absorption
realities modelled here). Absorption factors: Hurrell & Egli, *Am J Clin Nutr*
2010.

Units were verified against published values before being trusted — spinach
iron computes to 2.95 mg/100 g against a published ~2.7 mg. That check lives in
`backend/scripts/build_ifct.py`.

---

## Architecture

```
React 19 · Vite 8 · Tailwind 4
            │
            ▼
       FastAPI  (41 endpoints)
            │
     ┌──────┴───────┐
     ▼              ▼
orchestrator    deterministic services  ← no LLM, ever
  7 agents      ├─ nutrition_service      IFCT → USDA → flagged estimate
  (OpenAI)      ├─ micronutrient_service  ICMR RDA + absorption model
                ├─ clinical_safety        drug/condition rules + citations
                ├─ cost_optimizer         scipy linprog (HiGHS)
                ├─ household_service      per-person split + cooking plan
                ├─ fitness_service        Mifflin-St Jeor, leucine threshold
                ├─ gamification_service   streaks, XP, shields
                ├─ adaptation_service     live day state, next-meal guidance
                └─ scheduler_service      call windows, quiet hours
```

The agents (`diet_planner`, `food_vision`, `profile_health`,
`recommendation`, `progress_feedback`) handle language and judgement.
Arithmetic, adequacy, safety and optimisation are plain Python — reproducible
and testable. An LLM is not trusted with a warfarin interaction.

### Project layout

```
backend/
  app/
    agents/          LLM agents + their prompts
    api/             routes: chat, insights, agent (voice tools),
                     gamification, diet-plan, food-vision, health
    core/            LLM client, orchestrator
    data/            ifct2017.json (built), market_prices.json (SAMPLE),
                     indian_food_nutrition.json (legacy fallback)
    models/          SQLAlchemy models
    services/        the deterministic layer
  scripts/
    build_ifct.py    regenerates ifct2017.json from the IFCT CSV
  tests/
frontend/
  src/pages/         Chat, Household, DietPlan, Onboarding, Recommendations
  src/components/    LogCalendar, CallMeButton
  src/services/      api.js
docs/
  SIH_PRESENTATION_SCRIPT.md   6-slide presentation script
  sarvam_agent_setup.md        voice agent console walkthrough
  sarvam_tools.json            tool definitions to import
  architecture.md
```

---

## API reference

41 endpoints. Full interactive docs at `/docs` when running.

<details>
<summary><b>chat</b> — the conversational front door (8)</summary>

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/chat/agents` | sidebar agent list + data sources |
| GET | `/api/v1/chat/sessions` | list conversations |
| POST | `/api/v1/chat/sessions` | new conversation |
| GET | `/api/v1/chat/sessions/{id}` | one conversation |
| DELETE | `/api/v1/chat/sessions/{id}` | delete it |
| POST | `/api/v1/chat/sessions/{id}/message` | send a message, get a reply |
| GET | `/api/v1/chat/calendar` | 5-week logging grid |
| GET | `/api/v1/chat/calendar/{day}` | one day, resolved to nutrients |

</details>

<details>
<summary><b>insights</b> — the deterministic engines (7)</summary>

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/insights/micronutrients` | RDA adequacy + iron absorption model |
| POST | `/api/v1/insights/household` | per-person split of one dish |
| POST | `/api/v1/insights/optimize-cost` | cheapest basket closing nutrient gaps |
| POST | `/api/v1/insights/fitness` | energy/macro targets, leucine check |
| POST | `/api/v1/insights/safety` | clinical guardrail screen |
| GET | `/api/v1/insights/rda` | the ICMR RDA table used |
| GET | `/api/v1/insights/sources` | provenance for every number |

</details>

<details>
<summary><b>diet-plan</b> · <b>food-vision</b> · <b>gamification</b> (13)</summary>

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/diet-plan/generate` | generate a plan |
| GET | `/api/v1/diet-plan/current` | the saved plan |
| PATCH | `/api/v1/diet-plan/current` | edit one meal (nutrients recomputed server-side) |
| DELETE | `/api/v1/diet-plan/current` | discard it |
| POST | `/api/v1/food-vision/analyze` | meal photo → ingredients → nutrients |
| POST | `/api/v1/food-vision/confirm` | persist a user-corrected analysis |
| GET | `/api/v1/food-vision/sources` | data provenance |
| POST | `/api/v1/gamification/check-in` | complete a habit, earn XP |
| GET | `/api/v1/gamification/status/{user_id}` | streaks, level, shields |
| POST | `/api/v1/gamification/use-shield` | protect a streak |
| POST | `/api/v1/gamification/squad/create` | create an accountability group |
| GET | `/api/v1/gamification/squad/{id}` | squad standing |
| GET | `/api/v1/gamification/config` | level table + habit definitions |

</details>

<details>
<summary><b>agent</b> — voice agent tools & scheduling (14)</summary>

The five `tools/*` endpoints are what you register in the Sarvam console. All
require the `X-Agent-Key` header and **fail closed** if `AGENT_TOOL_KEY` is
unset.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/agent/tools/call_context` | briefing at call start |
| POST | `/api/v1/agent/tools/log_meal` | record what was eaten |
| GET | `/api/v1/agent/tools/plan_for_slot` | read the saved plan for a meal |
| GET | `/api/v1/agent/tools/day_state` | budget left today |
| POST | `/api/v1/agent/tools/safety_check` | mandatory before clinical answers |
| GET/POST | `/api/v1/agent/schedule` | read/set call schedule |
| GET | `/api/v1/agent/due` | which contacts are due now |
| POST | `/api/v1/agent/sarvam/call` | place an outbound call |
| GET | `/api/v1/agent/sarvam/config` | generated console config |
| POST | `/api/v1/agent/sarvam/detect-language` | language ID for vernacular text |
| POST | `/api/v1/agent/notify` | send a text update |
| POST | `/api/v1/agent/inbound/message` | inbound text webhook |
| GET | `/api/v1/agent/messaging/status` | configured channels |

</details>

---

## Voice agent setup (optional)

**Skip this entirely if you just want the web app.** Everything above works
without it.

Outbound calls need a [Sarvam Voice Agents](https://docs.sarvam.ai/conversations/overview)
account plus a **public HTTPS URL** — Sarvam's cloud has to reach your backend,
so `localhost` will not do.

```bash
# 1. expose the backend (cloudflared needs no signup; ngrok also works)
cloudflared tunnel --url http://localhost:8020

# 2. generate the console config against that public URL
curl "http://localhost:8020/api/v1/agent/sarvam/config?base_url=https://<tunnel-host>"
```

That response contains the system prompt, all five tool definitions with live
URLs, and a list of whatever is still blocking you. It is generated from the
running server, so it can never drift from the code.
See [`docs/sarvam_agent_setup.md`](docs/sarvam_agent_setup.md).

**Three things that will cost you an hour if you do not know them:**

1. **Voice Agents keys are a separate credential** from core Sarvam keys, and
   use the `X-API-Key` header — not `api-subscription-key`. Generating a new
   one **invalidates the old**.
2. **Every console edit creates a new agent version.** Keep
   `SARVAM_APP_VERSION` in step or calls run an old snapshot — including old
   tool URLs.
3. In the console, set `X-Agent-Key` to **Fixed value**, not "let the agent
   decide", or the model is asked to invent your secret and sends nothing.

---

## Environment variables

All live in `backend/.env`. See
[`backend/.env.example`](backend/.env.example) for the annotated list.
**Only `OPENAI_API_KEY` is required.**

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | **yes** | — | the only model provider |
| `DIET_PLANNER_MODEL` | no | `gpt-4o-mini` | |
| `RECOMMENDATION_MODEL` | no | `gpt-4o-mini` | |
| `FOOD_VISION_MODEL` | no | `gpt-4o` | needs vision |
| `DATABASE_URL` | no | `sqlite:///./nutrition_ai.db` | Postgres URL also works |
| `USDA_API_KEY` | no | `DEMO_KEY` | `DEMO_KEY` = 30 req/hr; [free key](https://api.data.gov/signup/) |
| `AGENT_TOOL_KEY` | for voice | — | empty ⇒ tool endpoints refuse everything |
| `SARVAM_*` | for voice | — | see `.env.example` |
| `TELEGRAM_*` / `TWILIO_*` | for texts | — | Telegram is the ~5 min option |

Generate an agent tool key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

---

## Known limitations

Stated rather than hidden — these are real and we would rather be visibly
incomplete than quietly wrong.

- **IFCT catalogues ingredients, not prepared dishes.** There is no "chapati"
  row. Dishes are decomposed into ingredients; prepared foods fall through to
  USDA, and the response says which tier answered.
- **IFCT 2017 does not measure vitamin B12 at all.** The app returns an
  explicit *"cannot assess B12"* with a recommendation to get a serum test.
  This matters enormously for vegetarian India.
- **Portion estimation from a single photo is the largest error source** — not
  food identification. The app shows the grams and asks you to confirm before
  logging.
- **`market_prices.json` is sample data**, labelled as such in the file and in
  every optimiser response. Replace with a real feed (Agmarknet, a retailer
  API, or user-entered local prices) before treating cost advice as accurate.
- **Composition tables list dry weights** for grains and pulses. A katori of
  *cooked* dal is ~30 g dry; using the cooked weight overstates calories ~3×.
  The prompts carry these conversions.
- **WhatsApp is roadmap, not built.** Production WhatsApp needs Meta Business
  verification (days). Telegram works today; the Twilio sandbox works for
  testing only.

---

## Tests

```bash
cd backend
pytest tests/ -q
```

---

## Attribution

- **IFCT 2017** — Longvah T, Ananthan R, Bhaskarachary K, Venkaiah K. *Indian
  Food Composition Tables.* National Institute of Nutrition, ICMR, Hyderabad,
  2017. Government publication; reproduction permitted with acknowledgement.
  Only the underlying data is used — no AGPL-licensed helper package is
  vendored.
- **USDA FoodData Central** — U.S. Department of Agriculture. Public domain.
- **ICMR-NIN** — *Nutrient Requirements for Indians: RDA and EAR*, 2020.
- **Iron bioavailability** — Hurrell R, Egli I. *Am J Clin Nutr*
  2010;91(5):1461S-7S.
- **Energy** — Mifflin MD et al. *Am J Clin Nutr* 1990 (Mifflin-St Jeor).
- **Protein** — ISSN position stands; leucine threshold ~2.5 g/meal.
- **Epidemiology** — NFHS-5 (anaemia); ICMR-INDIAB, *The Lancet* 2023
  (diabetes/prediabetes).

## License

MIT — see [LICENSE](LICENSE).
