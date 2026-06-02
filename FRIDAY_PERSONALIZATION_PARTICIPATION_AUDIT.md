# FRIDAY PERSONALIZATION & IDENTITY PARTICIPATION AUDIT

## Executive Summary
This audit investigates the structural disconnection between FRIDAY's **Identity Subsystem** and the active LLM reasoning engines. It details why the assistant hallucinates project details (such as Failure 4), maps disabled personalization features, and estimates the true level of active behavioral alignment.

---

## 1. Failure 4: "What project are we working on?" Identity Leak

### Observed Behavior
* **Query:** `"What project are we working on?"`
* **Observed Output:** Hallucinated project descriptions (claiming to work on generic web dev or unrelated platforms), or vague redirection.
* **Expected Output:** Concise recognition of the active "FRIDAY" project and current development workspace.

### The Diagnostic Evidence
During the diagnostic run, the system produced the following trace for identity manager dynamics:

```text
QUERY: "What project are we working on?"
--- IDENTITY MANAGER DYNAMICS ---
Relevance Score: 75.0
Influence Weight: 0.3
Behavior Directives injected into System Prompt:
== BEHAVIORAL DIRECTIVES & REASONING MODIFIERS ==
- PERSONALIZATION PRIORITY: Prioritize instructions in this strict hierarchy: ...
```
And yet, in the E2E latency test, the query resolved to `CLARIFICATION` and the spoken response was:
```text
"What would you like me to tell you about the project, Sir?"
```

### The Root Cause: Disjointed Context Flow
Although the `IdentityManager` successfully parses contextual slices (yielding user identity "Aaditya" and project "FRIDAY" as shown in the diagnostics), the active prompt generation is highly fragmented:

1. **System Prompt Divergence:** `groq_client.py` has a hardcoded `DEFAULT_SYSTEM_PROMPT` containing high-level identity claims. However, the dynamic contextual slices (e.g. `user_identity.academic_context` or `self_identity.project` details) are **only** injected in `action_executor.py` inside the `AI_QUERY` block.
2. **Direct Routing Bypass:** If a query is routed to any brain other than `AI_QUERY` (such as `RETRIEVAL`, `WEATHER`, `NEWS`, or `SPOTIFY_CONTROL`), `action_executor.py` bypasses the `AI_QUERY` block. It calls `ask_groq` directly without extracting `identity_slices` or `user_identity` profiles.
3. **No Active Codebase Connection:** The identity profile contains a static `relationship` and `architecture_context` string, but has no actual runtime knowledge of active directories, git branches, or the current file tree. When asked about the active project, the LLM either guesses based on vague conversational memory or returns a default clarification, completely blind to reality.

---

## 2. Clarification Request 4: Disconnection Audit

### Question A: How long has this disconnect existed?
This disconnect has existed since the **Phase 5 Persona & Behavior Contract Refactoring**. The architecture divided prompt building into two independent layers:
* `groq_client.py` (which injects dynamic behavioral signals such as verbosity, conciseness, and style directives).
* `action_executor.py` (which parses static database slices from `identity_profile.json`).

Because the actual identity profiles were never consolidated into the core `groq_client.py` pipeline, the LLM remained blind to the user's details for any non-conversational execution turn.

### Question B: Which personalization features were effectively disabled?
Due to this architectural gap, the following features were effectively disabled:
* **Academic/JEE Context Continuity:** The LLM could not adjust technical explanations based on Class 12 constraints during search-based or retrieval-based queries.
* **Hardware Adaptation:** The assistant could not optimize suggestions based on the user's primary mobile device (`OnePlus Nord CE 4 5G`) or local hardware constraints.
* **Focal Interest Alignment:** Dynamic interests (e.g. Marvel, Cinema, Startups) could not shape recommendations, as these slices were excluded from standard search/retrieval prompts.

### Question C: Behavioral Architecture Active Participation Estimates

We have evaluated the true active status of all personalization dimensions below:

| Personalization Dimension | Real Status | Active Participation % | Technical Diagnosis & Proof |
| :--- | :--- | :--- | :--- |
| **Response Style (Verbosity/Tone)** | **Fully Active** | **100%** | `groq_client.py` dynamically parses and appends style constraints (conciseness, low-fluff) into the system prompt on *every* Groq call. |
| **Planning Style** | **Bypassed** | **0%** | `PlannerBrain` is completely rule-driven and uses static trigger matrices, unaffected by the personalization engine. |
| **Explanation Style** | **Partially Active** | **30%** | Complies with conciseness and phrasing constraints, but ignores user interests or academic contexts during retrieval tasks. |
| **Decision Support** | **Bypassed** | **0%** | No decision tradeoff matrices are actively utilized at execution time. |
| **Relationship Continuity** | **Partially Active** | **40%** | Leverages short-term history, but cannot access user preference profiles or memory nodes dynamically. |
| **Identity Awareness** | **Bypassed** | **10%** | Heavily relies on hardcoded system prompts; dynamic identity profiles remain isolated. |
| **Project Awareness** | **Bypassed** | **0%** | Lacks any runtime hooks to resolve directory structures or workspace configurations. |
