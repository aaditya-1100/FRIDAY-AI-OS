# FRIDAY Production vs. Replay Gap Report

This report documents the architectural and testing discrepancies between FRIDAY's synthetic validation tests (which passed 100%) and the real-world production environment (which failed manual execution on multiple critical scenarios).

---

## 1. The Core Paradox: Why Replay Passed While Production Failed
The ultimate reason for this paradox is a **testing coverage boundary gap**. The synthetic replay validation suite (`tests/replay_validation.py`) operates in a sterile, mocked, and highly isolated subset of the codebase. It completely bypasses:
1. **The Post-LLM Validation Layer**: The buggy sanity filter in `intent_parser.py` that intercepts LLM outputs and overrides routing rules.
2. **The Execution & Verification Layers**: The native OS action executor, process scanners, and third-party API clients.
3. **Stateful Async Pipeline Coordination**: Subprocess spawning, network latency, and COM thread-local deadlocks.

---

## 2. In-Depth Gap Analysis by Scenario

### Gap 1: "Rust vs Python" Routing
* **Why Replay Passed**:
  * In [tests/replay_validation.py](file:///C:/FRIDAY/backend/tests/replay_validation.py#L82), `verify_case_1` checks:
    ```python
    dec = self.planner.plan("Rust vs Python", self.context_mgr, self.pref_mem, self.episodic_mem)
    ok = dec.target_brain == "LLM"
    ```
  * `PlannerBrain.plan` runs its weighted signal calculations, correctly scores `"recursion"` and `"code"` keywords, determines `"LLM"` is the winner, and returns `target_brain = "LLM"`. The test passes.
* **Why Production Failed**:
  * In the real-world runtime pipeline ([pipeline.py](file:///C:/FRIDAY/backend/core/pipeline.py#L536)), the system runs `PlannerBrain`, but then immediately dispatches the query to `parse_intent` to perform LLM-based structured JSON extraction.
  * Groq parses the query and returns `intent = "AI_QUERY"`.
  * The parser then runs `validate_intent_sanity` on the intent dictionary.
  * **The Stale Code Path**: A legacy regex shortcut block meant to separate YouTube-specific queries intercepts the turn because `"yt"` is a substring of `"python"`. The query is forced into a `YOUTUBE_TOPIC_SEARCH` route.
  * **The Integration Gap**: The replay validation suite only tests `PlannerBrain` routing, entirely omitting `parse_intent` and `validate_intent_sanity` post-processing from its execution paths.

---

### Gap 2: "Play a Rust tutorial" Execution
* **Why Replay Passed**:
  * Replay validation has **zero test cases** that execute actual media actions or verify active playback. It only tests basic conversational keywords or mocks SAPI thread failure recoveries.
* **Why Production Failed**:
  * In production, executing `"Play a Rust tutorial"` initiates a complex sequence of unmocked network scrapes and browser launches.
  * **Network Scraper Bypasses**: The YouTube scraper in `action_executor.py` tries to fetch live HTML from YouTube. In production, this call hit a scraping barrier/CAPTCHA or timed out (10s limit), returning `None`.
  * **Cold Start / Spawn Race Condition**: The system then falls back to browser search. On the first manual attempt, a cold subprocess spawn of Google Chrome timed out or threw a Windows registry lookup failure in `system/chrome_opener.py`.
  * **Strict Verifier Verification**: Since Chrome failed to open, the verifier returned `False`. The execution loop tried twice, failed both times, and returned `False`, prompting the pipeline to announce `"I could not do that sir"`.
  * **The Test Gap**: The validation framework is completely blind to live network timeouts, YouTube HTML changes, and local browser execution states.

---

### Gap 3: Long-Term Memory & Project Awareness
* **Why Replay Passed**:
  * Replay tests for memory are restricted to simple pronoun follow-ups (`verify_case_3`).
  * The test updates `self.context_mgr` with `"Explain recursion"`, runs `context_mgr.enrich_query("What are the rules of it?")`, and asserts that the string `"recursion"` is restored.
  * This is a simple context dictionary key-value swap, which works perfectly in memory.
* **Why Production Failed**:
  * Manual execution requires the system to actually write facts to disk ("Remember this project") and recall dynamic workspace locations.
  * **The Stub Bypass**: The file `backend/memory/long_term.py` contains exactly a one-line comment stub and absolutely no code. The LLM simply generated conversational compliance without writing a single bit.
  * **The Prompt Injection Bypass**: While `IdentityManager` parses relational slices (user academic constraints, preferred channels, active projects), the main conversation pipeline in `groq_client.py` *never* calls `id_mgr.get_contextual_slices(query)`.
  * **The Integration Gap**: The LLM system prompt is never enriched with the identity profile at runtime. The LLM remains fully blind to Aaditya's active workspace and profile variables, forcing it to hallucinate.

---

## 3. Structural Testing Gaps & Regression Summary

| Testing Tier | Mocked/Replay Behavior | Production Behavior | Discrepancy & Testing Gap |
| :--- | :--- | :--- | :--- |
| **Routing** | Stateless `PlannerBrain` keyword scoring. | Stateful `parse_intent` + `validate_intent_sanity` filters. | Bypasses the post-LLM validation filters, leaving substring match bugs fully hidden. |
| **Execution** | None. Completely omitted from tests. | Async `subprocess.Popen` launches, live `requests.get` scrapes. | Blind to network timeouts, scraping walls, CAPTCHAs, and Chrome executable path failures. |
| **Verification** | Simple boolean mocks. | Real-time `psutil` process scans, file path existence verification. | Bypasses process tracking logic; process startup latency is never measured. |
| **Memory** | Isolated context dictionary swaps. | Literal stub files (`long_term.py`), disconnected prompt injections. | Bypasses actual disk storage and prompt generation hooks. |
| **Audio/TTS** | Simulates SAPI5 recovery catches. | Background COM apartment initialization and device re-enumeration on every turn. | Blind to thread blockages and audio driver latencies. |

---

## 4. Next Step Architectural Directives
To achieve true production readiness, the testing suite must evolve from simple stateless planning assertions to **End-to-End Pipeline Integration Validation**. Mocks must be replaced with robust, sandboxed local execution checks, and all sanity post-filters must be fully run against all test case queries.
