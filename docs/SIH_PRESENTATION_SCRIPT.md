# NutriAI — SIH 2026 Round 2 Presentation Script

**Team:** ISOLATE · **Team ID:** SIH035 · **PS ID:** SIH26198
**Theme:** MedTech / BioTech / HealthTech · **Category:** Software
**Format:** 6 slides, 6 presenters

> This is the long version. Cut it down — do not add to it. Everything here is
> traceable to something that actually exists in the repository. If you cannot
> demo a claim, delete the claim.

---

## 0. The rubric is the script

Round 2 scores **7 criteria × 20 marks = 140**. Every criterion must be hit
explicitly by someone. If a criterion is never named out loud, the judge has
to infer it — and inference scores 3, not 5.

| # | Criterion (20) | Owned by | The sentence that earns it |
|---|---|---|---|
| 1 | **Clarity** | S1 + S2 | "India does not have a calorie problem. It has a micronutrient and metabolic problem." |
| 2 | **Novelty** | S2 + S3 | Absorption modelling, household split, ₹-per-nutrient LP — none exist in any Indian app |
| 3 | **Feasibility** | S3 + S5 | It is built and running now; 37 endpoints, live phone call |
| 4 | **Scale of Impact** | S4 | 57% of women anaemic, 101M diabetics — and it runs on a ₹6,000 phone |
| 5 | **Sustainability (SDGs)** | S4 | SDG 2, 3, 10, 12 + DPDP Act 2023 + ethical guardrails |
| 6 | **User Experience** | S2 + S4 | Voice call in Hindi, no app install, one photo for the whole family |
| 7 | **Future Work Progression** | S5 + S6 | ABDM/ABHA, CGM-free glycaemic personalisation, canteen B2B |

**Rule for all six speakers:** every number you say out loud must be followed
by its source. "57% — NFHS-5." "18.86 g protein — IFCT 2017." This single
habit is what separates us from a ChatGPT wrapper in a judge's mind.

---

## Slide 1 — Title & The Real Problem
**Presenter 1 · 60–75 seconds · Targets: Clarity (20)**

### On the slide
- SIH 2026 · PS ID **SIH26198** · Team **ISOLATE** (SIH035)
- Theme: MedTech / BioTech / HealthTech · Category: Software
- Title: **NutriAI — Not a calorie counter. A nutrition safety net.**
- Three statistics, large, with citations underneath

### Script

> "Good morning. We are Team ISOLATE, problem statement SIH26198, under
> MedTech and HealthTech.
>
> Before the solution, one correction to how this problem is usually framed.
>
> Every nutrition app in India is a calorie counter. But India's nutrition
> crisis is not calories.
>
> **Fifty-seven percent of Indian women aged 15 to 49 are anaemic. Sixty-seven
> percent of children under five are anaemic.** That is NFHS-5, the National
> Family Health Survey.
>
> **One hundred and one million Indians have diabetes. A hundred and thirty-six
> million more are prediabetic.** That is the ICMR-INDIAB study, published in
> The Lancet in 2023.
>
> That is not an obesity problem. That is **hidden hunger and metabolic
> disease** — and a calorie counter cannot see either of them.
>
> There is a second thing calorie counters cannot see. Indians do not eat from
> individual plates. **We eat from one pot.** One person cooks for the whole
> family — a diabetic father, a pregnant mother, an anaemic teenage daughter, a
> growing child — all from the same dish. Every app on the market assumes one
> person logging one plate.
>
> So our thesis is one sentence: **India does not have a calorie problem. It
> has a micronutrient and metabolic problem — and it eats from a shared pot, on
> a budget, in twenty languages. We built for that.**"

### Judge cue
Pause after the thesis sentence. Let it land. Then hand over.

### Rubric hooks — say these exact words
- "relevant to the problem statement" → name the PS ID and theme in the first breath
- Clarity is scored on *precision*, so give **numbers with sources**, not adjectives

---

## Slide 2 — The Idea & Solution
**Presenter 2 · 90–105 seconds · Targets: Clarity, Novelty, User Experience**

### On the slide
- One diagram: **Thali photo → per-person split → gap → ₹ basket → voice call**
- Six feature tiles, one line each
- Bottom strip: "Every number cites IFCT 2017 / ICMR-NIN RDA 2020"

### Script

> "So what did we build.
>
> NutriAI is a **micronutrient-first, multi-agent nutrition assistant** built on
> Indian food composition data, not American.
>
> Six things make it different from anything currently in the market.
>
> **One — the hidden hunger detector.** We track iron, calcium, zinc, vitamin A,
> vitamin C, folate, B6, B1, B2, niacin, potassium, phosphorus — not just
> macros. And then we do the part nobody does: **we model absorption, not just
> intake.**
>
> Here is why that matters. Tea and coffee polyphenols block up to **sixty
> percent** of non-heme iron absorption when taken with a meal. Vitamin C can
> **triple** it. Calcium competes with it. Phytates in wholegrains suppress it.
>
> So our app does not say "eat more iron". It says: **your iron intake is fine —
> your absorption is not. Move your chai ninety minutes after lunch and add
> lemon to your dal.** That is a recommendation no Indian app gives, and it is
> scientifically defensible — Hurrell and Egli, American Journal of Clinical
> Nutrition, 2010.
>
> **Two — household mode.** One photo of the thali. We split the nutrition
> across every family member, judged against *their own* ICMR requirement.
> Then we plan **one cooking session** that serves all four, with per-person
> tweaks instead of four separate dishes.
>
> **Three — the nutrition-per-rupee optimiser.** Zero apps optimise for cost.
> We take a weekly budget and solve for maximum nutrient closure per rupee.
> That is a **linear program, not an LLM** — reproducible, and it runs in
> milliseconds.
>
> **Four — Indian mixed-dish vision, done honestly.** Photo models fail on
> sambar, biryani and rajma because the calories hide in oil you cannot see.
> We do not claim we solved that. We classify the dish, ask **two questions** —
> home-cooked or restaurant, how much oil — and apply a cooking-method
> multiplier over Indian composition tables.
>
> **Five — the clinical safety guardrail.** This is what makes us MedTech and
> not fitness. I will let slide five cover it.
>
> **Six — voice, in your language, with no app install.** The people who need
> this most will not install an app or type in English."

### Judge cue
If short on time, cut features 4 and 6 here — they are covered again in S3 and S4.

---

## Slide 3 — Technical Approach
**Presenter 3 · 105–120 seconds · Targets: Novelty, Feasibility**

### On the slide
- Architecture: **React/Vite → FastAPI → 7 agents → data layer**
- The three-tier source chain, drawn as a waterfall
- "37 API endpoints · 542 foods · 18 amino acids · 19 micronutrients"

### Script

> "The architecture, and specifically the design decision the whole product
> rests on.
>
> **The data layer.** We use **IFCT 2017 — the Indian Food Composition Tables**,
> published by the National Institute of Nutrition, ICMR, Hyderabad. Five
> hundred and forty-two Indian foods, physically measured across six regions.
> Not USDA. Not a scraped website.
>
> We extracted the full panel: **nineteen micronutrients, eighteen amino acids,
> regional names in twelve languages**, and vegetarian tags. We verified our
> unit conversions against published values before trusting them — spinach iron
> came out at 2.95 mg per hundred grams against a published 2.7. That check is
> in our build script.
>
> **Nutrient resolution is a three-tier chain**, and this is the important part:
>
> - **Tier one — IFCT 2017.** Indian, lab-measured.
> - **Tier two — USDA FoodData Central.** For prepared and non-Indian foods.
> - **Tier three — an OpenAI estimate**, and it is **flagged in the response and
>   coloured amber in the UI**, because it was not measured by anyone.
>
> A judge should hear that clearly: **we never let an estimate impersonate
> measured data.**
>
> **The agent layer.** Seven agents behind one orchestrator — Diet Planner,
> Food Vision, Profile & Health, Recommendation, Progress, plus the
> deterministic Nutrition and Safety services. All on OpenAI.
>
> And the rule that governs every one of them: **the model never produces a
> nutrient number.** The vision agent outputs ingredient names and grams —
> nothing else. Every calorie, every milligram of iron comes from a lookup.
>
> **Why that matters.** Ask any LLM how much protein is in paneer and it will
> give you a confident, plausible, unverifiable number. Ours returns 18.86 grams
> per hundred, and tells you it came from IFCT 2017. **No citation, no claim.**
>
> **The deterministic layer.** Absorption modelling, ICMR RDA comparison, drug
> interactions, and the cost optimiser are all **pure Python — no LLM**. They
> are reproducible, testable, and fast. An LLM cannot be trusted with a
> warfarin interaction.
>
> Thirty-seven endpoints, running now. Happy to show any of them."

### The matcher story — use only if a judge asks about rigour
> "Our first food matcher used fuzzy string matching. It scored 'chapati'
> against 'Onion, stalk' at 0.69 and 'mango' against a Bengali word for quail
> meat at 0.91. We rewrote it token-level with a confidence floor. It now gets
> twelve out of twelve Indian foods right and correctly *rejects* six prepared
> dishes to the USDA tier. We would rather return nothing than return a
> confident wrong number."

---

## Slide 4 — Impacts and Benefits
**Presenter 4 · 90 seconds · Targets: Scale of Impact, Sustainability/SDGs, User Experience**

### On the slide
- Left: reach numbers. Right: SDG badges. Bottom: personas
- One line: **"Works on a ₹6,000 phone. No app install."**

### Script

> "Who this reaches, and what changes.
>
> **Scale.** The anaemia and diabetes numbers from slide one are the addressable
> population: that is **hundreds of millions of people**, not a niche.
>
> But reach is not the same as availability. Global nutrition apps are
> **app-only and English-first**, which prices out most of the country. So we
> built for the opposite constraint: **a voice call in Hindi, Marathi or Tamil.
> No app. No typing. No smartphone required.**
>
> We have this working. Our agent calls a real phone number, speaks Hindi,
> takes "aaj do roti aur dal khaya", converts household measures to grams,
> logs it against IFCT, and tells you what is left for the day. We placed that
> call this week.
>
> **Personas.** The anaemic teenage girl who gets a WIFS iron tablet but drinks
> chai with dinner and absorbs a fraction of it. The gestational-diabetic
> mother. The CKD patient who must cap potassium. The mother cooking one pot
> for four different requirements.
>
> **Sustainability and SDGs.** We map to four:
> - **SDG 2 — Zero Hunger**, specifically target 2.2 on micronutrient deficiency
> - **SDG 3 — Good Health and Wellbeing**, on non-communicable disease
> - **SDG 10 — Reduced Inequalities**: the cost optimiser and voice access exist
>   precisely so this is not a product only for people who can afford it
> - **SDG 12 — Responsible Consumption**: nutrient-per-rupee reduces waste and
>   favours local millets and pulses over imported protein
>
> **Ethics.** Three commitments, all implemented rather than promised:
> - Every recommendation carries its **source row**
> - The app **refuses** clinical questions and escalates to a dietitian
> - Voice calls are **opt-in per meal slot**, with enforced quiet hours from
>   9:30 pm to 7 am. The user can switch any of it off.
>
> On privacy we name the specific law: **the DPDP Act 2023.** Health data is
> sensitive personal data; our design keeps the food log local to the user's
> record with no third-party sharing."

---

## Slide 5 — Feasibility and Viability
**Presenter 5 · 105 seconds · Targets: Feasibility, Future Work Progression**

### On the slide
- "Built and running" checklist with endpoint counts
- Risk table: risk → mitigation
- Cost line

### Script

> "Feasibility. The short answer is that this is not a concept — it is running
> on this laptop right now.
>
> **What is built and demonstrable today:**
> - Thirty-seven API endpoints
> - IFCT 2017 fully extracted — 542 foods, 19 micronutrients, 18 amino acids
> - Absorption modelling, live
> - Household split across four members, live
> - The rupee optimiser solving with **scipy HiGHS**, live
> - Clinical guardrails with drug and condition rules, live
> - A voice agent that **actually called a phone and spoke Hindi**
> - A chat interface where every answer cites its source
>
> **Now the honest part, because feasibility is scored on realism.**
>
> IFCT catalogues **ingredients, not prepared dishes**. There is no 'chapati'
> row. We handle that by decomposing dishes into ingredients and falling
> through to USDA — and we tell the user which tier answered.
>
> IFCT **does not measure vitamin B12 at all**. That matters enormously for
> vegetarian India. We do not hide it: the app returns an explicit
> 'cannot assess B12' with a recommendation to get a serum test. We would
> rather be visibly incomplete than quietly wrong.
>
> **Portion estimation from a single photo is the largest error source** — not
> food identification. So we show the estimate and ask the user to confirm the
> grams before logging.
>
> **Risks and mitigations:**
>
> | Risk | Mitigation |
> |---|---|
> | Vision misreads a mixed dish | Two-question hybrid + user confirms grams |
> | Food missing from IFCT | USDA tier, then flagged estimate |
> | LLM hallucinating a number | Model never emits nutrients — architecturally prevented |
> | Clinical harm | Deterministic rule layer + hard refusal + dietitian escalation |
> | Cost of LLM calls | Deterministic layers are free; LLM only for vision and phrasing |
>
> **Viability.** Marginal cost per user is a few rupees a month, because the
> expensive parts — composition data, RDA comparison, optimisation — are local
> computation, not model calls.
>
> **Future progression**, which is a scored criterion, so specifically:
> - **ABDM / ABHA integration** — attach nutrition to the national health ID
> - **Glycaemic personalisation without a CGM** — learn from occasional
>   glucometer readings and advise meal sequencing
> - **Mess and canteen mode** — a natural B2B wedge we can pilot in our own
>   college canteen
> - **Vrat and festival intelligence** — Navratri, Ramadan, Ekadashi, Jain
>   no-root-vegetable
> - **Label scanner against ICMR salt/sugar/fat limits**
> - **pgvector semantic search** to replace exact-match food lookup"

---

## Slide 6 — Research and References
**Presenter 6 · 60–75 seconds · Targets: Clarity, Novelty (market research), Sustainability**

### On the slide
- Grouped citations, readable
- A short competitor table

### Script

> "Finally, what this is built on — because a nutrition claim without a citation
> is just an opinion.
>
> **Food composition:**
> - **IFCT 2017** — Indian Food Composition Tables, NIN, ICMR Hyderabad. Our
>   primary source.
> - **USDA FoodData Central** — fallback for prepared and non-Indian foods.
>
> **Requirements:**
> - **ICMR-NIN, Nutrient Requirements for Indians, RDA and EAR, 2020.** Note
>   these differ sharply from Western RDAs — iron for an Indian adult woman is
>   **29 mg**, far above the US figure, because of the absorption realities we
>   modelled.
>
> **Absorption science:**
> - **Hurrell & Egli**, Am J Clin Nutr 2010 — iron bioavailability; the
>   ascorbate, polyphenol, calcium and phytate factors in our model.
>
> **Epidemiology:**
> - **NFHS-5** — anaemia prevalence
> - **ICMR-INDIAB, The Lancet 2023** — diabetes and prediabetes
>
> **Clinical:**
> - **KDIGO** for CKD nutrition · **ACR** for gout · **FSSAI/ICMR** antenatal
>   guidance · standard anticoagulation guidance for warfarin–vitamin K
>
> **Performance and protein:**
> - **Mifflin-St Jeor**, Am J Clin Nutr 1990 — energy
> - **ISSN position stands** — protein intake and the ~2.5 g per-meal leucine
>   threshold for muscle protein synthesis
>
> **Where we sit against the market:**
>
> | | Global apps | Indian apps | NutriAI |
> |---|---|---|---|
> | Composition base | USDA | Mixed/scraped | **IFCT 2017 (ICMR)** |
> | Micronutrients | Rarely | Rarely | **19 tracked** |
> | Absorption modelling | No | No | **Yes** |
> | Household split | No | No | **Yes** |
> | Cost optimisation | No | No | **Yes (LP)** |
> | Clinical guardrails | No | No | **Yes** |
> | Voice, vernacular | No | No | **Yes** |
>
> One closing line. Every other app tells you **what you ate**. We tell you
> **what your body actually absorbed, whether it is safe with your medication,
> and what it costs to fix.**
>
> Thank you."

---

## The 90-second live demo

If given a laptop, run **one flow**, not six features:

1. **Thali photo** → ingredients and grams
2. **Household split** → four members, four verdicts from one dish
3. **"Priya absorbs 1.19 mg of the 21 mg iron on her plate"**
4. **Toggle chai timing** → absorbed iron more than doubles. *This is the moment.*
5. **₹14 basket** closes the week's iron and protein gap
6. **The phone rings**, and it speaks Hindi

Then stop. Do not show anything else.

---

## Q&A — the eight questions you will get

**"Is this just a ChatGPT wrapper?"**
> "The opposite. The model is architecturally forbidden from producing a
> nutrient number. It names ingredients and estimates grams. Every calorie and
> milligram comes from IFCT or USDA. Absorption, RDA comparison, drug
> interactions and cost optimisation are pure Python with zero model calls."

**"How accurate is the photo analysis?"**
> "Food identification is good. **Portion estimation is the weak link and we
> say so** — it is the largest error term. That is exactly why we ask two
> questions about cooking method and oil, and why we show the grams for the
> user to correct before logging. Anyone claiming 95% accuracy on a photo of
> sambar is not being straight with you."

**"What if the food is not in your database?"**
> "Three tiers. IFCT, then USDA, then a model estimate that is explicitly
> flagged and shown in amber. The user always knows which tier answered."

**"Where does B12 come from — that is the vegetarian issue?"**
> "It does not, and that is a real limitation we surface rather than hide.
> IFCT 2017 does not measure B12. The app says 'cannot assess' and recommends
> a serum test. Adding a B12 source is on the roadmap."

**"Is the medical advice safe?"**
> "We do not give medical advice. A deterministic rule layer screens every
> output. CKD and pregnancy trigger a **hard block** and a dietitian referral.
> Warfarin plus vitamin K produces a warning with a citation. We never name a
> drug or a dose."

**"How is this different from HealthifyMe?"**
> "Four things they do not do: micronutrient absorption modelling, household
> per-person split, cost optimisation, and clinical drug-food guardrails. And
> they are built on Western composition data for an Indian plate."

**"Can it scale?"**
> "The expensive layers are local computation, not model calls, so cost per
> user is nearly flat. IFCT is 526 KB in memory. The path to scale is pgvector
> for semantic food search and ABDM integration for identity."

**"What is left to build?"**
> "WhatsApp Business API needs Meta verification — days, not code. Real market
> price feeds — currently sample data, clearly labelled as such in the file.
> And B12 composition data."

---

## Speaker discipline — read before you present

1. **Never say a number without its source.** This is the single highest-value
   habit in the room.
2. **Name the limitation before the judge finds it.** B12, portion error, and
   sample prices. Volunteering a weakness reads as competence; being caught
   hiding one reads as the opposite.
3. **Do not claim a feature we have not run.** WhatsApp is *roadmap*. Say
   roadmap.
4. **Say "IFCT 2017" and "ICMR" out loud at least once each.** Judges are
   listening for whether you used the Indian reference or the American one.
5. **Hand over cleanly.** "…and Presenter 3 will take the architecture."
6. If you blank, fall back to the thesis: *India does not have a calorie
   problem. It has a micronutrient and metabolic problem.*

---

## Timing

| Slide | Presenter | Target | Hard cap |
|---|---|---|---|
| 1 Title & Problem | P1 | 70 s | 90 s |
| 2 Idea & Solution | P2 | 100 s | 120 s |
| 3 Technical Approach | P3 | 115 s | 135 s |
| 4 Impacts & Benefits | P4 | 90 s | 110 s |
| 5 Feasibility & Viability | P5 | 105 s | 125 s |
| 6 Research & References | P6 | 70 s | 85 s |
| **Total** | | **~9 min** | **~11 min** |

Leave at least three minutes for Q&A. If you are running long, cut from
slide 2 (features repeat later), never from slide 5 (feasibility is 20 marks
and the most commonly under-argued criterion).
