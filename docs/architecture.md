# Nutrition AI Assistant - Architecture

## Current State (Phase 1)
Currently, the application implements a subset of the full architecture to provide a working end-to-end flow:
1. **Diet Planner Agent:** Generates day-by-day structured meal plans.
2. **Recommendation Agent:** Generates real-time suggestions and swaps based on adherence.
3. **Static Nutrition Data:** A seeded JSON list of Indian foods provides macro data instead of a live vector search.

These agents are routed via `app/core/orchestrator.py`, which simply looks them up in a registry and calls `.run()`.

## Target Architecture (Phase 2+)

The final system will feature 6 agents. The `Orchestrator` will act as a Graph coordinator (likely migrating to LangGraph) rather than a simple router, managing state transitions between:

1. **Profile & Health Agent** 
   - Handles the initial onboarding conversation.
   - Extracts medical conditions and clarifies ambiguous inputs before passing structured data to the planner.
2. **Food Vision Agent**
   - Takes image uploads from the user's meal.
   - Identifies the food and estimates portion size.
3. **Nutrition Analysis Agent (Replacing JSON Seed)**
   - Takes identified food strings and queries a Vector Database (`pgvector` in PostgreSQL).
   - Uses semantic search to find the closest match in a massive food database, returning accurate macros.
4. **Diet Planning Agent** *(Implemented)*
5. **Recommendation Agent** *(Implemented)*
6. **Progress & Feedback Agent**
   - Consumes the execution logs of the Orchestrator and the user's historical adherence.
   - Periodically generates a weekly/monthly progress report and adjusts the user's base goals.

### Where new components plug in:
- **Agents:** Add new agent classes inheriting from `BaseAgent` in `app/agents/` and register them in `Orchestrator.registry`.
- **Vector DB:** `pgvector` will run inside the existing Postgres container. The `NutritionService` will be updated to query the database using SQLAlchemy instead of loading the static `indian_food_nutrition.json`.
