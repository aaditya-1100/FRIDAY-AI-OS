# FRIDAY AI Assistant — Architectural Open Questions & Decisions

## 1. Trigger Learning: Formal Definition of Failure

### 1.1 Taxonomy of System Interruptions
To implement the Trigger Learning Layer, we must establish a clear mathematical boundary between **Routing/Trigger Failures** (which reflect modeling errors and should degrade trigger reliability) and **Execution/API Failures** (which reflect environment errors and should *never* degrade trigger reliability).

```
                              SYSTEM INTERRUPT
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
     [ Model / Routing Failure ]                     [ Environmental Failure ]
     - User Correction (y = -1)                      - API / Network Outage (y = 0)
     - Implicit Cancellation (y = -1)                - Device / HW Block (y = 0)
     - Target App Mismatch (y = -1)                  - Third-Party Error (y = 0)
              │                                               │
     Updates Reliability (EMA)                      Bypasses Reliability Update
```

We formally classify system interruptions into the following categories:

| Event Class | Context Indicator | Learning Signal ($y_t$) | Architectural Action | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Wrong Routing** | User corrects command with explicit semantic shift within 5 seconds. | $y_t = -1$ | Degrade $R(T)$ via EMA log-odds update. | Direct evidence that the routing parser selected an incorrect category. |
| **Wrong Trigger** | User immediately cancels action (e.g. *"stop that"*, *"close window"*). | $y_t = -1$ | Degrade $R(T)$ via EMA log-odds update. | Direct evidence that the trigger was pulled in error. |
| **API Outage** | Network requests return timeout or HTTP 5xx codes (e.g., Spotify API down). | $y_t = 0$ | Bypassed. No update to reliability. | The trigger selection was correct, but execution failed due to external systems. Penalty would cause starvation. |
| **Executor Failure** | Local OS command fails due to permission blocks or lock contention. | $y_t = 0$ | Bypassed. No update to reliability. | System state issue. Must be resolved by OS/admin recovery, not routing degradation. |
| **User Correction (Implicit)** | User re-issues query with expanded details (e.g., *"open spotify"* $\rightarrow$ *"open spotify app"*). | $y_t = -1$ | Bypaded or minor penalty ($y_t = -0.5$). | Represents semantic refinement, indicating the first trigger was slightly off or fumbled. |

### 1.2 Mathematical Safety Boundary
To prevent temporary network drops from corrupting the reliability engine:
$$y_t = \begin{cases} 
   -1.0 & \text{if User\_Correction\_Detected} = \text{True} \\
   +1.0 & \text{if Action\_Succeeded} = \text{True} \land \text{User\_Correction\_Detected} = \text{False} \\
   \text{null} & \text{if Execution\_Failed\_Ext\_API} = \text{True} \lor \text{Network\_Outage\_Detected} = \text{True} 
\end{cases}$$

---

## 2. Confidence Fusion: Mathematical & Comparative Justification

To aggregate individual sub-module confidences into a unified turn confidence ($C_{\text{unified}}$) without triggering false warnings, we evaluate four mathematical fusion architectures.

### 2.1 Comparative Analysis Matrix

| Method | Mathematical Complexity | Latency Impact | Zero-Component Vulnerability | Dynamic Recalibration Flexibility |
| :--- | :--- | :--- | :--- | :--- |
| **1. Weighted Geometric Mean** | Low ($O(N)$) | $< 1\text{ms}$ | **CRITICAL**. A single $C_i = 0$ collapses the score to $0$ regardless of weight. | Low (static weights). |
| **2. Bayesian Networks** | Extremely High | $15\text{--}45\text{ms}$ (requires propagation) | Moderate (handles noise but requires strict joint conditional matrices). | Very Low (requires massive training sets to estimate prior distributions). |
| **3. Factor Graphs** | High | $10\text{--}30\text{ms}$ (requires message-passing) | Low (can model marginals but computationally expensive). | Low (manually defined message-passing factors). |
| **4. Reliability-Aware Bayesian Fusion (RABF)** | **Low** ($O(N)$) | **$< 1\text{ms}$** | **ZERO**. Non-relevant components are dynamically masked out ($\beta_i = 0$). | **High (relevance masks are compiled dynamically per intent).** |

### 2.2 Mathematical Proof of RABF Superiority over Geometric Mean
Under the Weighted Geometric Mean model:
$$C_{\text{geom}} = \prod_{i=1}^{N} C_i^{w_i}$$
If the user issues a query *"what is 45 x 12"*, the memory subsystem is not engaged. It returns $C_{\text{memory}} = 0.0$ (since no vector search context matches). This collapses the entire turn confidence:
$$C_{\text{geom}} = C_{\text{asr}}^{w_1} \times C_{\text{intent}}^{w_2} \times C_{\text{routing}}^{w_3} \times (0.0)^{w_4} = 0.0$$
This forces a false low-confidence alert.

Under the RABF model:
$$C_{\text{unified}} = \frac{\sum_{i=1}^{N} \beta_i \cdot w_i \cdot C_i}{\sum_{i=1}^{N} \beta_i \cdot w_i}$$
For this query, the pre-routing planner sets $\beta_{\text{memory}} = 0$, completely isolating the zero-value dimension. The unified confidence evaluates strictly to the weighted average of speech, intent, and routing confidences (e.g. $0.98$), ensuring silent, flawless execution.

### 2.3 Complexity vs. Latency Justification
While Bayesian Networks and Factor Graphs offer robust probabilistic modeling, they introduce significant latency and calibration overhead. A full Bayesian belief propagation pass takes up to $30\text{ms}$ on CPU, adding to the execution pipeline. RABF performs simple scalar matrix multiplication ($< 1\text{ms}$ on CPU) and requires zero dynamic probability training, ensuring that FRIDAY maintains an extremely tight, instantaneous voice feedback loop.

---

## 3. Dependency Parsing: Library Selection & Budgets

To extract grammatical structures and command verbs, we must establish a clear boundary for NLP dependencies.

### 3.1 Selected Library: spaCy (`en_core_web_sm`)
We select **spaCy** utilizing the lightweight `en_core_web_sm` model.
* **Rejected Alternatives**:
  - *Stanza (Stanford NLP)*: Rejected due to heavy CPU execution times (latency $> 150\text{ms}$ per query) and high memory footprint ($> 1\text{GB}$ VRAM/RAM).
  - *NLTK*: Rejected due to lack of a native, high-performance syntactic dependency parser (requires manual tree traversal wrappers).
* **Selected Model Rationale**:
  - *spaCy* processes standard queries in **$< 12\text{ms}$** on a standard CPU.
  - The `en_core_web_sm` model has a memory footprint of only **$12\text{--}15\text{MB}$ RAM**, making it highly suitable for running locally in a background worker process.

### 3.2 Performance and Latency Budgets

```
[ User Query Input ]
         │
         ├─── spaCy Dependency Parsing ───► Target: < 15ms (Max Cap: 25ms)
         │
         ├─── Semantic Preprocessing   ───► Target: < 10ms (Max Cap: 15ms)
         │
         └─── Trigger Arbitration      ───► Target: < 5ms  (Max Cap: 10ms)
```

We establish strict operational budgets for the pre-routing planning pipeline:

| Pipeline Step | Target Latency | Max Latency Cap | RAM Limit |
| :--- | :--- | :--- | :--- |
| **Semantic Preprocessing** | $5\text{ms}$ | $15\text{ms}$ | $< 5\text{MB}$ |
| **spaCy Dependency Parsing** | $12\text{ms}$ | $25\text{ms}$ | $< 20\text{MB}$ |
| **Trigger Arbitration** | $3\text{ms}$ | $10\text{ms}$ | $< 2\text{MB}$ |
| **Total Pre-Routing Pass** | **$20\text{ms}$** | **$50\text{ms}$** | **$< 27\text{MB}$** |

### 3.3 Rule-Based Fallback Parser (Robustness Path)
If the spaCy model fails to initialize (e.g. missing virtual environment package or lock error), the pipeline seamlessly falls back to a **Syntactic Pattern Scanner** to avoid system failure:
1. **Verbs & Nouns Extraction**: Execute a lightweight part-of-speech scanner using word-boundary regular expressions and verb lookup lists.
2. **Grammar Mapping**: Reconstruct the verb-object relationship:
   - Match `"explain \b\w+\b"` or `"what is \b\w+\b"` $\rightarrow$ Map to `AI_QUERY` with high syntactic confidence.
   - Match `"play \b\w+\b tutorial"` or `"show video \b\w+\b"` $\rightarrow$ Map to `MEDIA_PLAY` with high syntactic confidence.
3. **Safety Fallback**: If both spaCy and the rule-based scanner are blocked, the system defaults to the semantic intent vector ($I(T)$) to make its routing decision.

---

## 4. Risk Mitigation & Implementation Decisions Summary

| Operational Area | Primary Risk | Core Mitigation | Frozen Architectural Decision |
| :--- | :--- | :--- | :--- |
| **Dependency Latency** | spaCy adds startup delay or cold-boot latency. | Initialize the `spacy.load` session asynchronously in a background thread during the boot sequence. | spaCy SM model is pre-loaded during early boot stage (`main.py` init), and is fully active before voice activation. |
| **Reliability Starvation** | EMA learning loop permanently blocks a trigger due to false corrections. | Bound the reliability score with a lower floor: $R(T) \ge 0.15$. | Implementation must enforce $R_{\text{floor}} = 0.15$ in the database model and provide an automated CLI reset tool. |
| **Context Pronoun Drift** | Context manager incorrectly enriches a pronoun, leading to wrong intent. | Syntactic parser verifies that the enriched query maintains structural verb-object consistency with the original query. | If pronoun enrichment changes the root verb of the query, the original un-enriched query is preserved. |
