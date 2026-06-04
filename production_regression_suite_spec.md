# FRIDAY PRODUCTION REGRESSION SUITE SPECIFICATION

## Executive Summary
This document specifies the design, scope, and technical assertions of the permanent **FRIDAY Production Regression Suite** (`backend/tests/test_production_regression.py`). 

The purpose of this suite is to serve as a guardrail, ensuring future architectural improvements never break basic production reliability or re-introduce the critical failures identified in our audits.

---

## 1. Test Harness Design & Environment
* **Test File:** `backend/tests/test_production_regression.py`
* **Test Framework:** Standard Python `unittest` or `pytest` with `asyncio` support.
* **Environment Context:** Mocked environment configs loading preference, semantic, and episodic stubs to guarantee high execution speed and 100% deterministic assertion behavior without triggering real-world system side effects (like actually launching a physical Chrome window).

---

## 2. Regression Test Specifications

Below are the 7 core test groups specified with query entries, mock fixtures, and strict technical assertions:

### Test Group 1: Intent Routing Boundaries (Sovereignty Verification)
* **Query under test:** `"Rust vs Python"`
* **Target brain from Planner:** `LLM`
* **Mock Fixtures:** Loaded `PlannerBrain`, empty `ContextManager`.
* **Execution Flow:**
  1. `PlannerBrain.plan(query)` resolves `target_brain = "LLM"`.
  2. The planner output is passed as `planner_hint` to `parse_intent()`.
  3. `parse_intent` calls the parser and processes results via `validate_intent_sanity`.
* **Technical Assertions:**
  * Assert that the resolved intent is `"AI_QUERY"` or `"REALTIME_QUERY"`.
  * Assert that the intent is **not** re-routed or overridden to `"YOUTUBE_TOPIC_SEARCH"` or any media intent.
  * Assert that `validate_intent_sanity` forbids cross-domain re-routing under the `"LLM"` brain boundary.

### Test Group 2: Media Action Routing
* **Query under test:** `"Play a Rust tutorial"`
* **Target brain from Planner:** `MEDIA`
* **Mock Fixtures:** Loaded `PlannerBrain`, warm `EpisodicMemory`.
* **Technical Assertions:**
  * Assert that `PlannerBrain.plan(query)` selects `target_brain = "MEDIA"`.
  * Assert that `parse_intent` resolves the intent to `"PLAY_MEDIA"` with `query = "rust tutorial"`.

### Test Group 3: Memory Write Verification (Write-Read Loop)
* **Query under test:** `"Remember FRIDAY is my AI project"`
* **Target brain from Planner:** `MEMORY`
* **Mock Fixtures:** Fresh writable `SemanticMemory` instance pointing to a temporary json path.
* **Execution Flow:**
  1. Parse intent of query $\rightarrow$ assert resolved intent is `"SET_FACT"`.
  2. Invoke `execute_action` with `intent_data = {"intent": "SET_FACT", "query": "Remember FRIDAY is my AI project"}`.
  3. The executor calls `semantic_mem.add_fact("AI project", "FRIDAY")` and reloads the memory from disk.
* **Technical Assertions:**
  * Assert that the file is written to disk and the loaded size is greater than zero bytes.
  * Assert that `semantic_mem.get_fact("AI project")` returns exactly `"FRIDAY"`.
  * Assert that the final conversational response confirms verified success: *"I have committed and verified that in my semantic registry, Sir."*

### Test Group 4: Project Awareness Authority Hierarchy
* **Queries under test:** `"What project are we working on?"` & `"What is the current project?"`
* **Mock Fixtures:** Active workspace directory bound to `C:\FRIDAY`. Loaded `ActiveProjectRegistry` metadata file containing project `"FRIDAY"`.
* **Execution Flow:**
  1. Call `ProjectManager.get_active_project()` $\rightarrow$ verify it binds the project registry.
  2. Call the prompt context enrichment pipeline.
* **Technical Assertions:**
  * Assert that the `ActiveProjectRegistry` context outranks and overrides other memory facts.
  * Assert that the active project block is injected into the authoritative system prompt with `project_name = "FRIDAY"` and `workspace_path = "C:\\FRIDAY"`.

### Test Group 5: Pronoun & Context Continuity (Multi-Turn Resolution)
* **Multi-Turn Script:**
  1. Turn 1: `"Tell me about Apple"`
  2. Turn 2: `"What is their primary product?"`
  3. Turn 3: `"Who currently runs it?"`
* **Mock Fixtures:** `ShortTermMemory` context manager.
* **Execution Flow:**
  1. Run Turn 1 $\rightarrow$ assert intent resolves to `"AI_QUERY"` / `"REALTIME_QUERY"`. Append turn to history.
  2. Run Turn 2 $\rightarrow$ ContextManager enriches query by parsing history.
  3. Run Turn 3 $\rightarrow$ ContextManager enriches query.
* **Technical Assertions:**
  * Assert that for Turn 2, the query after context resolution is rewritten to explicitly refer to `"Apple's"` (e.g. *"What is Apple's primary product?"*).
  * Assert that for Turn 3, the pronoun `"it"` is successfully resolved and rewritten to `"Apple"` (e.g. *"Who currently runs Apple?"*).

### Test Group 6: Native App Launch
* **Query under test:** `"Open VS Code"`
* **Technical Assertions:**
  * Assert that the resolved intent is `"OPEN"` with `target = "VS Code"`.

### Test Group 7: Multi-Intent Parsing (Compound Actions)
* **Query under test:** `"Open VS Code and explain recursion"`
* **Technical Assertions:**
  * Assert that the parser maps the query to the `"MULTI_ACTION"` intent.
  * Assert that the `actions` array contains exactly two distinct nested intent dictionaries:
    1. `{"intent": "OPEN", "target": "VS Code"}`
    2. `{"intent": "AI_QUERY", "query": "explain recursion"}`

---

## 3. Execution Framework & Continuous Integration
To run the suite, a developer or deployment script executes:

```powershell
# Run the regression suite
C:\FRIDAY\.venv\Scripts\pytest C:\FRIDAY\backend\tests\test_production_regression.py -v
```

This regression suite will be integrated as a pre-commit hook and a release gate. **Any future merge or codebase update must pass 100% of these test cases to be considered production-ready.**
