# FRIDAY AI Assistant — Trigger Intelligence Validation

## 1. Benchmark Methodology

To guarantee routing correctness under high semantic complexity, the Trigger Intelligence subsystem must undergo rigorous testing. We define a multi-stage offline and online **Dynamic Routing Benchmark Pipeline**.

```
                ┌───────────────────────────────────┐
                │   Semantic Evaluation Database    │
                │     (1,500+ Annotated Queries)     │
                └─────────────────┬─────────────────┘
                                  │
                                  ▼
                ┌───────────────────────────────────┐
                │   Inference Simulator Engine      │
                │    (Injects Synthetic Noise)      │
                └─────────────────┬─────────────────┘
                                  │
                                  ▼
                ┌───────────────────────────────────┐
                │     Deterministic Replay Test     │
                │   (Validates Historic Regressions)│
                └─────────────────┬─────────────────┘
                                  │
                                  ▼
                ┌───────────────────────────────────┐
                │   Dynamic Telemetry Aggregator    │
                │    (Measures Production Margin)   │
                └───────────────────────────────────┘
```

### 1.1 Synthetic Dataset Generation
The benchmark runs against an annotated test set of $1,500$ queries spanning $15$ unique command domains. The dataset consists of:
1. **Direct Commands ($40\%$)**: Syntactically clean commands (e.g. *"open VS Code"*, *"play lofi music"*).
2. **Compound/Multi-Action Queries ($20\%$)**: Queries containing multiple operations linked by conjunctions (e.g. *"open chrome and start stopwatch"*).
3. **High-Ambiguity Bait Queries ($30\%$)**: Explicitly designed to overlap across trigger boundaries (e.g. *"play rust tutorial"* vs. *"explain rust"*).
4. **Conversational Noise ($10\%$)**: Fumbled audio transcripts, vocal filler, and background environmental noise (e.g. *"uh... let me think, close spotify"*).

### 1.2 Multi-Turn Simulation Testing
To certify the Trigger Learning Layer (historical reliability EMA and correction decay), we simulate **Synthetic Session Profiles**. A test runner injects mock user feedback over a series of $K=10$ turns:
* **Nominal Path**: Query is issued $\rightarrow$ Trigger fires $\rightarrow$ Simulator returns $y_t = +1$ (no correction).
* **Corrective Path**: Query is issued $\rightarrow$ Trigger fires $\rightarrow$ Simulator immediately follows with a semantic correction command (e.g., *"no, close that"* or *"stop it"*) within $\Delta t < 5\text{ seconds}$ $\rightarrow$ Test engine registers $y_t = -1$ and asserts that $R_t(T)$ decays mathematically according to specifications.

---

## 2. Statistical Target Metrics (Precision & Recall)

The routing engine must meet strict **Precision** ($P$) and **Recall** ($R$) floor constraints to pass the CI/CD deployment gateway. Let the set of queries belonging to target intent $T$ be $Q_T$, the set of queries predicted as intent $T$ be $\hat{Q}_T$, and the intersection of correctly predicted queries be $TP_T = Q_T \cap \hat{Q}_T$:

$$P_T = \frac{\left| TP_T \right|}{\left| \hat{Q}_T \right|}, \quad R_T = \frac{\left| TP_T \right|}{\left| Q_T \right|}$$

### 2.1 Domain-Specific Performance Target Floors

| Trigger Class ($T$) | Target Precision Floor ($P_T$) | Target Recall Floor ($R_T$) | Operational Boundary Rationale |
| :--- | :--- | :--- | :--- |
| **SYSTEM_STATUS** | $\ge 98.0\%$ | $\ge 95.0\%$ | Accidental triggers block the voice output with heavy CPU charts; must be highly precise. |
| **TEMPORAL** | $\ge 99.0\%$ | $\ge 98.0\%$ | Zero tolerance for missed alarms, timers, or reminders. |
| **MEDIA_PLAY** | $\ge 95.0\%$ | $\ge 94.0\%$ | Needs high recall to support conversational and slang music requests without failing. |
| **NATIVE_OS (App Launch)**| $\ge 97.0\%$ | $\ge 96.0\%$ | Must not accidentally boot heavy apps (e.g. Chrome) on casual conversational filler. |
| **BROWSER** | $\ge 94.0\%$ | $\ge 92.0\%$ | Must trigger cleanly on absolute URLs and query-bounded web requests. |
| **AI_QUERY (Cognitive)** | $\ge 96.0\%$ | $\ge 98.0\%$ | The ultimate fallback; must absorb all timeless knowledge requests. |
| **CASUAL_CHAT** | $\ge 98.0\%$ | $\ge 99.0\%$ | Must suppress command execution entirely on casual greetings. |

---

## 3. Confusion Matrix Design

A dedicated **Routing Confusion Matrix** is generated after each validation run to trace leakage between adjacent classification boundaries.

```
                            PREDICTED TRIGGER (OUTPUT)
                 ┌──────────────────────────────────────────────────────────┐
                 │ NATIVE_OS │ MEDIA_PLAY │ TEMPORAL │ AI_QUERY │ SYSTEM    │
    ──┬──────────┼───────────┼────────────┼──────────┼──────────┼───────────┤
      │ NATIVE_OS│   TP_os   │   Leak_om  │  Leak_ot │  Leak_oq │  Leak_os  │
    A ├──────────┼───────────┼────────────┼──────────┼──────────┼───────────┤
    C │ MEDIA_PL │  Leak_mo  │   TP_media │  Leak_mt │  Leak_mq │  Leak_ms  │
    T ├──────────┼───────────┼────────────┼──────────┼──────────┼───────────┤
    U │ TEMPORAL │  Leak_to  │   Leak_tm  │   TP_temp│  Leak_tq │  Leak_ts  │
    A ├──────────┼───────────┼────────────┼──────────┼──────────┼───────────┤
    L │ AI_QUERY │  Leak_qo  │   Leak_qm  │  Leak_qt │   TP_ai  │  Leak_qs  │
      ├──────────┼───────────┼────────────┼──────────┼──────────┼───────────┤
      │ SYSTEM   │  Leak_so  │   Leak_sm  │  Leak_st │  Leak_sq │   TP_sys  │
    ──┴──────────┴───────────┴────────────┴──────────┴──────────┴───────────┘
```

### 3.1 Primary Leaking Junctions and Mitigation
The confusion matrix is evaluated for three primary structural leaks:
1. **MEDIA_PLAY $\rightarrow$ AI_QUERY** (e.g., *"Play Rust"* classified as explanation).
   * *Mitigation*: The Syntactic Parser increases $C_{\text{dependency}}$ for `MEDIA_PLAY` whenever `Play` acts as the root verb.
2. **AI_QUERY $\rightarrow$ NATIVE_OS** (e.g., *"Explain VS Code"* boots the editor).
   * *Mitigation*: Bounded by grounding checks; if the direct object is preceded by an explanatory verb, the grounding score $C_{\text{grounding}}$ is bypassed in favor of pure semantic intent.
3. **CASUAL_CHAT $\rightarrow$ REALTIME_QUERY** (e.g., *"how are you today"* triggers weather).
   * *Mitigation*: Explicit temporal filters remove greeting phrases from the freshness signal calculator.

---

## 4. Replay Validation and Regression Stability

To prevent behavioral regression as the system evolves, we implement a **Deterministic Log Replay Engine**.

### 4.1 Replay Runner Logic
1. **Extract Log Payload**: Parse production telemetry files to extract historical turns that resulted in corrections or low confidence.
2. **Initialize Environment State**: Reconstruct the exact system environment state captured in the log (active assistant state, memory cache, trigger reliability matrix).
3. **Re-Inject Query**: Feed the raw query into the updated Trigger Intelligence engine.
4. **Assert Stability**: Assert that the updated routing score either selects the correct target trigger or increases the margins ($\Delta S$) over the runner-up:
   $$S_{\text{unified}}(\text{Target}) - S_{\text{unified}}(\text{Competitor}) > \text{Baseline Margin}$$

---

## 5. Live Production Telemetry Schema

All online routing calculations and feedback logs are committed to `backend/data/routing_telemetry.db` in a structured format:

```sql
CREATE TABLE routing_telemetry (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    query TEXT NOT NULL,
    system_state TEXT NOT NULL,
    winner TEXT NOT NULL,
    runner_up TEXT NOT NULL,
    winning_score REAL NOT NULL,
    runner_up_score REAL NOT NULL,
    margin REAL NOT NULL,
    is_tiebreak_invoked BOOLEAN NOT NULL,
    confidence_score REAL NOT NULL,
    execution_latency_ms INTEGER NOT NULL,
    correction_received BOOLEAN DEFAULT FALSE,
    correction_latency_sec REAL,
    feedback_signal INTEGER DEFAULT 0 -- (-1 = Corrected, +1 = Successful)
);
```

### 5.1 Analytics Pipeline
A background worker parses telemetry data hourly to compute operational KPIs:
* **Correction Rate (CR)**: $\frac{\sum \text{Corrections}}{\sum \text{Turns}}$. Must stay below $1.5\%$.
* **Average Margin ($\bar{M}$)**: $\mathbb{E} \left[ S(\text{Winner}) - S(\text{Runner\_Up}) \right]$. Measures system decisiveness. If $\bar{M}$ falls below $0.15$, it alerts the developers to perform prototype recalibration.
* **Execution Latency ($L_{95}$)**: 95th-percentile routing processing time. Must stay below $150\text{ms}$.
