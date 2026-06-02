# FRIDAY AI Assistant — Master Evolution Implementation Plan

## 1. Executive Summary & Synthesis

The approved architectural blueprints:
1. `FRIDAY_TRIGGER_INTELLIGENCE_ARCHITECTURE.md` (Trigger Intelligence routing)
2. `FRIDAY_TRIGGER_CONFLICT_ENGINE.md` (Stateless syntactic conflict tie-breaking)
3. `FRIDAY_UNIFIED_CONFIDENCE_ARCHITECTURE.md` (Reliability-Aware Bayesian turn confidence)
4. `FRIDAY_RESPONSE_BEHAVIOR_ARCHITECTURE.md` (Proactive behavior planner & constraints)

These documents collectively resolve all remaining foundational correctness flaws in the FRIDAY system. The master plan synthesizes these into a highly synchronized, phase-wise development roadmap. It establishes the correct implementation order, dependencies, risk mitigation policies, and rollback playbooks to guide developers during coding.

---

## 2. Phase-Wise Implementation Roadmap

The implementation is structured into five distinct phases, progressing from structural foundations to advanced learning layers.

```
┌────────────────────────────────────────────────────────┐
│ Phase 1: Unified Confidence Foundation                 │
│ - Implement RABF Formula & Calibration Matrix in main  │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Phase 2: Dynamic Trigger Intelligence & planner.py     │
│ - Integrate I(T), C(T), R(T) into PlannerBrain.plan()  │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Phase 3: Conflict Tie-Breaker & Syntactic Parser       │
│ - Integrate Fused Conflict Score & Dependency Rules    │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Phase 4: Proactive Response Planning & Constraints     │
│ - Refactor behavior_contract.py & prompt enforcer      │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Phase 5: Trigger Learning & Implicit Feedback Loops    │
│ - Implement EMA logs-odds updates & correction monitor │
└────────────────────────────────────────────────────────┘
```

### 2.1 Phase 1: Unified Confidence Foundation (Target: Days 1-2)
* **Goal**: Implement the Reliability-Aware Bayesian Fusion (RABF) model in the core pipeline to eliminate false-positive low-confidence alerts.
* **Component Modifications**:
  - Modify `backend/main.py` pipeline loop: replace the multiplicative joint product with the RABF formula:
    $$C_{\text{unified}} = \frac{\sum \beta_i w_i C_i}{\sum \beta_i w_i}$$
  - Integrate the **Relevance Mask Matrix** mapping intents to active components.
  - Implement the **Confidence Threshold Policy**:
    - High ($\ge 0.85$): Silent execution.
    - Medium ($0.55\text{--}0.85$): Execute with implicit confirmation (modify `voice/speak.py` or output templates).
    - Low ($< 0.55$): Block and prompt for active clarification.
* **Verification**: Run `python test_system.py` to verify that optional modules (e.g. Memory) do not collapse turn confidence when they return low retrieval scores.

### 2.2 Phase 2: Dynamic Trigger Intelligence (Target: Days 3-4)
* **Goal**: Replace static priority routing in `backend/brain/planner.py` with the dynamic Trigger Score formula:
  $$S_{\text{trigger}}(T) = I(T) \times C_{\text{cap}}(T) \times R(T) \times W_{\text{priority}}(T)$$
* **Component Modifications**:
  - Update `PlannerBrain` in `backend/brain/planner.py`:
    - Incorporate baseline priority weights $W_{\text{priority}}$ for system status, temporal, media, and conversational queries.
    - Add dynamic capability confidence checks $C_{\text{cap}}$ (e.g., checking if Spotify API is online or local binaries are present).
    - Initialize reliability scores $R(T)$ from a persistent configuration file.
* **Verification**: Direct commands like *"open notepad"* and conversational fallbacks must route cleanly with dynamic confidence vectors.

### 2.3 Phase 3: Conflict Tie-Breaker & Syntactic Parser (Target: Days 5-6)
* **Goal**: Implement the stateless Conflict Engine and Syntactic Dependency Parser to disambiguate overlapping commands.
* **Component Modifications**:
  - Implement a grammatical dependency scanner in `backend/brain/planner.py` to identify ROOT verbs, direct objects, and noun modifiers.
  - Program rules to distinguish explanatory verbs (*"explain"*, *"what is"*) from action verbs (*"play"*, *"open"*).
  - Implement the **Fused Conflict Score** ($S_{\text{conflict}}$) calculation with the calibrated weight vector:
    $$w = [0.45, 0.25, 0.15, 0.10, 0.05]$$
  - Add the weak state prior $\Psi_{\text{state}}$ as the lowest weight dimension.
* **Verification**: Verify that *"Explain Rust"* routes to cognitive LLM and *"Play Rust tutorial"* routes to Media Play, even when the system is in `TASK_MODE`.

### 2.4 Phase 4: Proactive Response Planning (Target: Days 7-8)
* **Goal**: Refactor the response generation pipeline to proactively enforce behavioral contracts and negative constraints.
* **Component Modifications**:
  - Refactor `backend/brain/behavior_contract.py`:
    - Expand `BehaviorContract` to support token budgets, structured response skeletons, and negative topic lists.
    - Inject strict system prompt negative constraints (Zero-Tolerance boundaries for Stanford, JEE, PhD, Marvel) directly in `llm/response_generator.py`.
  - Implement the **Validation Layer**:
    - Add a post-generation fuzzy scanner that intercepts responses before TTS.
    - If a restricted token escapes, trigger the local Self-Correction Loop or fall back to a safe default response.
* **Verification**: Verify that bait prompts asking for credentials or universities never return Restricted Terms (Stanford, JEE, PhD) in the output.

### 2.5 Phase 5: Trigger Learning & Feedback Loops (Target: Days 9-10)
* **Goal**: Establish the Trigger Reliability Layer to allow the routing system to adapt based on success and failures.
* **Component Modifications**:
  - Add a persistent telemetry recorder for routing execution in `backend/data/routing_telemetry.db` or a JSON file.
  - Implement the **User Correction Monitor**:
    - Track the next $N=2$ user turns for negative sentiment or corrective commands (*"no wait"*, *"wrong application"*).
  - Implement the log-odds EMA update rule:
    $$\Phi_t(T) = \Phi_{t-1}(T) + \eta(T)(y_t - \sigma(\Phi_{t-1}(T)))$$
  - Add temporal decay and rollback safeties (reliability floors at $0.15$ and manual resets).
* **Verification**: Simulate a series of fumbled execution turns and verify that $R(T)$ drops appropriately, causing the router to favor highly reliable alternative triggers.

---

## 3. Risks & Rollback Playbook

| Risk Scenario | Criticality | Detection Metric | Preventive Action | Rollback Playbook (Step-by-Step) |
| :--- | :--- | :--- | :--- | :--- |
| **Trigger Starvation** (Reliability of a primary trigger drops too low, preventing it from ever being selected). | **HIGH** | $R(T) < 0.20$ logged repeatedly in telemetry. | Maintain a hard floor $R_{\text{floor}} = 0.15$ and enable fast-pass recovery on successful turns. | 1. Execute `admin_reset_reliability(T)` via CLI.<br>2. Restore the trigger's log-odds score to baseline $\Phi_0(T)$.<br>3. Inspect the error log to determine if the underperforming module has a persistent hardware/API block. |
| **Speech Engine Delay** (The syntactic parser or semantic validator adds execution latency). | **MEDIUM** | Pipeline execution latency exceeds $2.5\text{s}$. | Run regex/token hash validations synchronously; execute deep semantic reviews in a non-blocking background thread. | 1. If latency is $>2\text{s}$, bypass the semantic validator.<br>2. Fall back to lightweight regex negative constraints.<br>3. Log the query for offline profiling. |
| **Bayesian Prior Drift** (Unusual user behavior patterns bias the state prior $\Psi_{\text{state}}$, leading to misrouting). | **LOW** | System starts misrouting basic queries despite high intent confidence. | Cap the state prior weight at $w_5 = 0.05$. | 1. Disable the state prior contribution ($w_5 = 0.0$).<br>2. Recalibrate the state matrix weights using the integration test suite. |

---

## 4. Architectural Consistency Audit Checklist

Prior to beginning code implementation, the developer must perform this cross-document consistency audit:

- [x] **Conflict vs. Arbitration Boundaries**: Verify that the tie-breaking Conflict Score is only calculated when the difference between the top Trigger Scores is within $\epsilon = 0.05$. This prevents unnecessary computing overhead.
- [x] **State Context Partitioning**: Ensure that the assistant state (TASK_MODE) only contributes to the state context prior ($\Psi_{\text{state}}$) during a tie-break ($w_5=0.05$), and is never used as an active gate in the primary PlannerBrain score calculation.
- [x] **Confidence vs. Reliability Separation**: Confirm that Turn Confidence ($C_{\text{unified}}$) is used strictly to determine user confirmation prompts (implicit vs explicit), while Trigger Reliability ($R(T)$) is used strictly as a historical routing modifier. They must not be interchanged.
- [x] **Proactive Constraints Integration**: Verify that all negative constraints (Stanford, JEE, PhD, Marvel) are injected at the LLM prompting stage, and that the validation layer only acts as a safety checker (rather than the primary style manager).
