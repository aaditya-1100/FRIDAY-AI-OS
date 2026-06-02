# FRIDAY AI Assistant — Trigger Intelligence Architecture

## 1. System Redesign: Trigger Priority to Trigger Intelligence

### 1.1 The Limitations of Static Priority Routing
In early iterations of personal assistants, routing decisions were determined using a static priority matrix where each trigger class $T$ was assigned a constant priority weight:
$$Priority(T) \in [1, 10]$$
For example, `COGNITIVE_TASK` was assigned a static weight of $8$, while `MEDIA_PLAY` was assigned a weight of $5$. Under this model:
$$Winner = \arg\max_{T} Priority(T)$$

This static approach introduces **hidden routing debt**. A query such as *"Explain Rust"* and *"Play Rust tutorial"* both contain the high-salience token `"Rust"`. However:
1. *"Explain Rust"* expects a cognitive explanation (a programming language primer).
2. *"Play Rust tutorial"* expects media playback (a video guide).

Under static priority, if `COGNITIVE_TASK` dominates `MEDIA_PLAY`, both queries get routed to the cognitive engine. Conversely, if `MEDIA_PLAY` dominates, the system attempts to search for a video for a simple coding question. Patching this with regex rules is unsustainable as capabilities scale across media, search, workspace integration, coding, memory, and spatial mapping.

### 1.2 The Dynamic Trigger Intelligence Model
To achieve highly adaptive and context-aware routing, the static priority matrix is replaced by a dynamic **Trigger Intelligence Score** ($S_{\text{trigger}}$) calculated for each candidate trigger $T$ upon receiving a user query $Q$ in state $C$:

$$S_{\text{trigger}}(T \mid Q, C) = I(T \mid Q) \times C_{\text{cap}}(T) \times R(T) \times W_{\text{priority}}(T)$$

Where:
- $I(T \mid Q) \in [0, 1]$ represents **Semantic Intent Score** — the probability that the query maps to the trigger's domain based on NLU/semantic parsing.
- $C_{\text{cap}}(T) \in [0, 1]$ represents **Capability Confidence** — the self-assessed confidence of the trigger's target module in being able to fulfill the request given active hardware, software state, and entity resolution.
- $R(T) \in [0, 1]$ represents **Trigger Reliability** — the running historical reliability of the trigger, updated dynamically via reinforcement learning.
- $W_{\text{priority}}(T) \ge 0$ represents **Priority Weight** — a weak structural prior that biases routing toward critical safety/temporal operations without overriding strong semantic signals.

---

## 2. Mathematical Formulations of the Routing Dimensions

### 2.1 Semantic Intent Score: $I(T \mid Q)$
The semantic intent is computed using a dual-path pipeline combining a fast local bi-encoder and a high-order generative LLM parser:
$$I(T \mid Q) = \beta \cdot P_{\text{bi-encoder}}(T \mid Q) + (1 - \beta) \cdot P_{\text{LLM}}(T \mid Q)$$
- $\beta \in [0, 1]$ is a balancing coefficient (default: $0.4$).
- $P_{\text{bi-encoder}}(T \mid Q)$ is the cosine similarity of the query embedding $E(Q)$ to the trigger's prototype embedding $E(T)$ in a joint vector space.
- $P_{\text{LLM}}(T \mid Q)$ is the intent probability extracted from the structured JSON output of the LLM parser.

### 2.2 Capability Confidence: $C_{\text{cap}}(T)$
Capability confidence ensures that a trigger is not pulled if the underlying execution environment cannot support it:
$$C_{\text{cap}}(T) = \prod_{d \in \text{Deps}(T)} \text{Status}(d)$$
Where $\text{Status}(d) \in [0, 1]$ is checked dynamically:
- For `SPOTIFY_CONTROL`: returns $1.0$ if the local Spotify client is active or API is authenticated, and $0.0$ otherwise.
- For `MAP_ROUTE`: returns $1.0$ if GPS coordinates are available and geocoding services are online.
- For `NATIVE_OS` (App Launch): returns $0.95$ if the target application binary is verified on the OS path, and $0.20$ if it requires a fuzzy desktop search.

### 2.3 Priority Weight: $W_{\text{priority}}(T)$
Priority weights act as weak priors rather than hard gates. They prevent accidental misrouting of high-criticality commands without blocking semantic intent:

| Trigger Class | Baseline Weight ($W_{\text{priority}}$) | Operational Rationale |
| :--- | :--- | :--- |
| **SYSTEM_STATUS / EMERGENCY** | $1.25$ | Safety and system recovery operations |
| **TEMPORAL** | $1.15$ | Alarms, timers, and high-precision reminders |
| **MEDIA / BROWSER / NATIVE_OS** | $1.00$ | Standard execution triggers |
| **AI_QUERY / CASUAL_CHAT** | $0.85$ | Conversational and cognitive fallback |

---

## 3. Trigger Reliability & The Learning Layer (Change 5)

### 3.1 Historical Reliability: $R(T)$
The reliability score $R(T)$ is a moving historical performance metric that quantifies the long-term success of trigger $T$. It prevents the system from repeatedly executing a broken router path:
$$R_t(T) = \sigma \left( \Phi_t(T) \right)$$
Where $\Phi_t(T)$ is the log-odds of successful execution, and $\sigma(x)$ is the standard sigmoid function:
$$\sigma(x) = \frac{1}{1 + e^{-x}}$$

### 3.2 The Reinforcement Learning Update Rule
After each turn $t$, the system registers an execution signal $y_t \in \{-1, +1\}$ for the active trigger $T$:
- $y_t = +1$ (Success): Action successfully executed, and no correction was received.
- $y_t = -1$ (Failure/Correction): Action resulted in an error, or the user issued a correction.

The log-odds reliability score is updated using an Exponential Moving Average (EMA) with a variable learning rate $\eta(T)$:
$$\Phi_t(T) = \Phi_{t-1}(T) + \eta(T) \cdot \left( y_t - \sigma(\Phi_{t-1}(T)) \right)$$

### 3.3 Dynamic Temporal Decay
In the absence of active reinforcement, a trigger's reliability score slowly regresses toward the nominal baseline $\Phi_0(T)$ to allow repaired systems to regain trust:
$$\Phi_t(T) = \Phi_{t-1}(T) \cdot e^{-\lambda \cdot \Delta t} + \Phi_0(T) \cdot \left(1 - e^{-\lambda \cdot \Delta t}\right)$$
Where:
- $\lambda$ is the decay constant (default: $1.15 \times 10^{-6} \text{ s}^{-1}$, which equates to a half-life of approximately one week).
- $\Delta t$ is the time elapsed (in seconds) since the last execution.

### 3.4 Telemetry and Learning Feedback Loops

```
                   [ User Voice Input ]
                            │
                            ▼
                [ Trigger Arbitration ]
                            │
                   Execute Trigger (T)
                            │
                            ▼
              ┌─────────────┴─────────────┐
              ▼                           ▼
      [ System Action ]           [ Conversational LLM ]
              │                           │
              └─────────────┬─────────────┘
                            ▼
               [ User Correction Monitor ] (Next N turns)
                            │
              Is Correction Query Detected?
              ├── YES ──► y = -1 (Failure)
              └── NO  ──► y = +1 (Success)
                            │
                            ▼
                [ Reliability Update Engine ]
                            │
                     Update R_t(T)
```

#### Implicit Correction Monitoring
The system monitors the next $N=2$ user turns for semantic indicators of correction, such as:
1. Immediate cancellation commands: *"no wait"*, *"stop that"*, *"cancel"*.
2. Repeated execution with modification: User asks *"play rust"* (routed to YouTube app), then immediately says *"no, I mean explain rust"*.
3. Explicit negative sentiment: *"that is not what I wanted"*, *"wrong app"*.

### 3.5 Rollback Safeguards and Floors
To ensure that a trigger is never permanently starved or disabled due to transient noise:
1. **Reliability Floor**: $R(T)$ is bounded by a lower limit:
   $$R(T) \ge R_{\text{floor}} = 0.15$$
2. **Fast-Pass Recovery**: If a trigger's reliability has dropped below $0.5$, a single verified successful turn (e.g., explicit positive reinforcement like *"yes, that's it"*) triggers a fast-pass recovery step:
   $$\Phi_t(T) = \max(\Phi_t(T), \Phi_0(T))$$
3. **Hard Rollback Trigger**: If $R(T)$ falls below $0.25$, the system triggers a diagnostics warning in the logs and permits a manual rollback to the default prior configuration via `admin_reset_reliability(T)`.

---

## 4. Trigger Arbitration and Conflict Resolution

### 4.1 Arbitration Engine Pipeline
1. **Token Parsing**: Extract core entities, verbs, and noun phrases.
2. **Dimension Calculation**: Calculate $I(T)$, $C_{\text{cap}}(T)$, $R(T)$, and $W_{\text{priority}}(T)$ for all registered triggers.
3. **Score Assembly**: Compute the unified trigger score $S_{\text{trigger}}(T)$.
4. **Candidate Selection**: Rank triggers by $S_{\text{trigger}}(T)$.
5. **Tie-Breaking Check**: If the gap between the top two triggers is less than a margin $\epsilon = 0.05$:
   $$\left| S_{\text{trigger}}(T_1) - S_{\text{trigger}}(T_2) \right| < \epsilon$$
   Invoke the **Trigger Conflict Engine** to perform high-resolution syntactic and contextual tie-breaking.
6. **Execution Dispatch**: Pass the winning trigger to the execution router.

---

## 5. Telemetry & Log Schema

Every routing decision is captured in a telemetry payload to allow analysis of routing behaviors and dynamic calibration:

```json
{
  "timestamp": "2026-06-02T09:56:12Z",
  "query": "Play Rust tutorial",
  "resolved_intent": "VIDEO_BY_TITLE",
  "state_context": {
    "active_mode": "TASK_MODE",
    "last_app_launched": "chrome",
    "recent_corrections_count": 0
  },
  "arbitration_matrix": [
    {
      "trigger": "MEDIA_PLAY",
      "semantic_intent_score": 0.92,
      "capability_confidence": 1.0,
      "historical_reliability": 0.94,
      "priority_weight": 1.0,
      "final_score": 0.8648
    },
    {
      "trigger": "COGNITIVE_TASK",
      "semantic_intent_score": 0.88,
      "capability_confidence": 1.0,
      "historical_reliability": 0.96,
      "priority_weight": 0.85,
      "final_score": 0.71808
    }
  ],
  "winner": "MEDIA_PLAY",
  "margin": 0.14672,
  "execution_status": "PENDING",
  "feedback_loop": {
    "monitored_turns": 0,
    "has_correction": false,
    "final_signal": null
  }
}
```

---

## 6. Verification Strategy & Simulation Tests

To ensure the trigger intelligence engine is robust, a suite of deterministic simulation tests is run prior to deployment:

```python
# test_trigger_intelligence.py
import pytest
from brain.planner import PlannerBrain

def test_rust_routing_disambiguation():
    planner = PlannerBrain()
    
    # "Explain Rust" -> Expects LLM / Cognitive routing
    dec_explain = planner.plan("Explain Rust")
    assert dec_explain.target_brain == "LLM"
    
    # "Play Rust tutorial" -> Expects MEDIA routing
    dec_play = planner.plan("Play Rust tutorial")
    assert dec_play.target_brain == "MEDIA"

def test_trigger_reliability_decay():
    # Simulate a trigger failing repeatedly
    trigger_reliability = 0.95
    failures = 3
    for _ in range(failures):
        # Update reliability with failure signal
        trigger_reliability = update_reliability(trigger_reliability, signal=-1)
    
    assert trigger_reliability < 0.60
    
    # Ensure it decays back towards base prior over simulated time
    restored_reliability = simulate_temporal_decay(trigger_reliability, delta_time=604800) # 1 week
    assert restored_reliability > trigger_reliability
```

This verification strategy guarantees that the assistant scales organically as new capabilities are introduced, completely avoiding the routing debt of hardcoded priority lists.
