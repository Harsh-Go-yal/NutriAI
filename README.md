# NutriAI — Not a calorie counter. A nutrition safety net.

> India does not have a calorie problem. It has a micronutrient and metabolic
> problem — and it eats from a shared pot, on a budget, in twenty languages.
> We built for that.

**Smart India Hackathon 2026 · PS SIH26198 · MedTech / HealthTech · Team ISOLATE**

NutriAI is a multi-agent nutrition assistant built on **Indian food composition
data**, not American. It tracks micronutrients, models how much iron you
actually *absorb* (not just eat), splits one family dish across every member
against their own ICMR requirement, finds the cheapest way to close a nutrient
gap, screens every recommendation for drug–food interactions, and can phone you
in Hindi to log a meal.

Every nutrient number the app produces cites the composition table row it came
from. The language model is architecturally forbidden from inventing one.

---

## What it does

| Feature | What makes it different |
|---|---|
| **Hidden-hunger detector** | 19 micronutrients from IFCT 2017, judged against ICMR-NIN RDA 2020 — and an **absorption model**: tea with a meal cuts non-heme iron uptake ~60%, vitamin C triples it. The app tells you to move your chai, not just "eat more iron". |
| **Household mode** | One thali photo → split across every family member → four different verdicts on one pot → one cooking session with per-person tweaks. |
| **Nutrition-per-rupee optimiser** | A linear program (scipy/HiGHS) that closes your nutrient gaps at minimum cost. Not an LLM; reproducible. |
| **Honest Indian food vision** | The model names ingredients and estimates grams only. Two questions (home/restaurant, oil level) drive a cooking-method multiplier. Portions are shown for you to correct. |
| **Clinical safety layer** | Deterministic rules: warfarin↔vitamin K, metformin↔B12, levothyroxine↔calcium; CKD/gout/pregnancy guardrails; hard refusal + dietitian escalation. Every finding cites its source. |
| **Voice check-ins** | Scheduled outbound calls in Hindi/Marathi/Tamil via Sarvam. Opt-in per meal slot, enforced quiet hours, user can switch any of it off. |
| **Chat front door** | Ask anything; the assistant routes to the right service. Plans, logs and assessments are all persisted. |
| **Habit streaks** | XP, levels, streak shields, squads. DB-backed so a restart never resets a streak. |

### Data sources, in the order they are consulted

1. **IFCT 2017** — Indian Food Composition Tables, National Institute of
   Nutrition (ICMR), Hyderabad. 542 foods, lab-measured across six regions.
   Macros, 19 micronutrients, 18 amino acids, regional names in 12 languages.
   Committed as `backend/app/data/ifct2017.json`.
2. **USDA FoodData Central** — prepared dishes and non-Indian foods IFCT lacks.
3. **OpenAI estimate** — last resort only, **flagged in the response and shown
   in amber in the UI**. Never passes as measured data.

Requirements come from **ICMR-NIN RDA 2020**. Absorption factors follow
Hurrell & Egli, *Am J Clin Nutr* 2010.

---

## Quickstart

### Prerequisites

- Python 3.11+ · Node 18+ · an [OpenAI API key](https://platform.openai.com/)
- No database setup needed — SQLite is the default.

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# open .env and set OPENAI_API_KEY (everything else can stay at defaults)

uvicorn app.main:app --host 127.0.0.1 --port 8020 --reload
```

Backend: <http://localhost:8020> · Swagger: <http://localhost:8020/docs>

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env        # points at http://localhost:8020/api/v1
npm run dev
```

App: <http://localhost:5173/chat>

### 3. Try it

In the chat:

- *How much protein is in 150 g paneer?* → cites IFCT 2017
- *I had 2 roti and a katori of dal for lunch* → logs it, calendar updates
- *how much iron did I absorb if I had chai with it* → the absorption story
- *close my gaps under 200 rupees* → LP-optimised basket
- *make me a meal plan* → generated and saved; *what is my plan for dinner* reads it back

### Docker (Postgres + Redis)

```bash
cp backend/.env.example backend/.env   # set OPENAI_API_KEY
docker compose up --build
```

Backend on `:8000`, frontend on `:5173`.

---

## Voice agent (optional)

Outbound calls need a [Sarvam Voice Agents](https://docs.sarvam.ai/conversations/overview)
account and a public URL for the tool endpoints (Sarvam's cloud has to reach
your backend). The setup pack is generated live from the running server so it
can never drift from the code:

```bash
# start a tunnel, e.g.
cloudflared tunnel --url http://localhost:8020

# then fetch the console config with that URL
curl "http://localhost:8020/api/v1/agent/sarvam/config?base_url=https://<tunnel-host>"
```

That response contains the system prompt, the five tool definitions with live
URLs, and a list of anything still blocking you. Paste it into the console;
see [`docs/sarvam_agent_setup.md`](docs/sarvam_agent_setup.md) for a
walkthrough. Set the `SARVAM_*` variables in `backend/.env`.

**Two things that bite:** Voice Agents keys are a different credential from
core Sarvam keys and use `X-API-Key`, not `api-subscription-key`; and every
edit in the console creates a new agent version — keep `SARVAM_APP_VERSION`
in step.

---

## Architecture

```
React 19 / Vite / Tailwind 4
        │
        ▼
FastAPI  ──  orchestrator  ──  7 agents (OpenAI)
        │                      diet_planner · food_vision · profile_health
        │                      recommendation · progress_feedback · ...
        │
        └──  deterministic services (no LLM)
             nutrition_service      IFCT → USDA → flagged estimate
             micronutrient_service  ICMR RDA + absorption model
             clinical_safety        drug/condition rules, citations
             cost_optimizer         scipy linprog (HiGHS)
             household_service      per-person split + cooking plan
             fitness_service        Mifflin-St Jeor, leucine threshold
             gamification_service   streaks, XP, shields
             scheduler / adaptation voice call windows, dynamic day state
```

The rule that governs it: **the model never produces a nutrient number.** The
vision agent outputs ingredient names and grams. Every calorie and milligram
comes from a lookup, and every response carries its `source`.

### Project layout

```
backend/
  app/
    agents/        LLM agents + prompts
    api/           routes: chat, insights, agent (voice tools), gamification, ...
    core/          LLM client, orchestrator
    data/          ifct2017.json (built), market_prices.json (SAMPLE)
    models/        SQLAlchemy models
    services/      the deterministic layer
  scripts/
    build_ifct.py  regenerates ifct2017.json from the IFCT CSV
  tests/
frontend/
  src/pages/       Chat, Household, DietPlan, Onboarding, Recommendations
  src/components/  LogCalendar, CallMeButton, ...
docs/
  SIH_PRESENTATION_SCRIPT.md
  sarvam_agent_setup.md
```

---

## Environment variables

All in `backend/.env` — see [`backend/.env.example`](backend/.env.example)
for the full annotated list. Only `OPENAI_API_KEY` is required to run.

| Group | Needed for |
|---|---|
| `OPENAI_API_KEY`, `*_MODEL` | everything |
| `USDA_API_KEY` | fallback lookups (`DEMO_KEY` works, 30 req/hr) |
| `SARVAM_*`, `AGENT_TOOL_KEY` | voice calls |
| `TELEGRAM_*` / `TWILIO_*` | text notifications |

`AGENT_TOOL_KEY` guards the endpoints the voice agent calls. If it is unset
those endpoints refuse every request rather than defaulting to open.

---

## Known limitations — stated, not hidden

- **IFCT 2017 catalogues ingredients, not prepared dishes.** There is no
  "chapati" row. Dishes are decomposed into ingredients; prepared foods fall
  through to USDA.
- **IFCT does not measure vitamin B12.** The app returns "cannot assess" rather
  than guessing. This matters for vegetarian diets.
- **Portion estimation from a photo is the largest error source.** The app
  shows the grams and asks you to confirm before logging.
- **`market_prices.json` is sample data**, labelled as such in the file and in
  every optimiser response. Replace with a real price feed before treating
  cost advice as accurate.
- **Composition tables list dry weights** for grains and pulses. A katori of
  cooked dal is ~30 g dry; the prompts carry these conversions, but a wrong
  one overstates calories ~3×.

---

## Tests

```bash
cd backend && pytest tests/ -q
```

---

## Data attribution

- **IFCT 2017**: Longvah T, Ananthan R, Bhaskarachary K, Venkaiah K. *Indian
  Food Composition Tables.* National Institute of Nutrition, ICMR, Hyderabad,
  2017. Government publication; reproduction permitted with acknowledgement.
  Only the underlying data is used — no AGPL-licensed helper package is
  vendored.
- **USDA FoodData Central**: U.S. Department of Agriculture. Public domain.
- **ICMR-NIN**: *Nutrient Requirements for Indians — RDA and EAR*, 2020.

## License

MIT — see [LICENSE](LICENSE).
