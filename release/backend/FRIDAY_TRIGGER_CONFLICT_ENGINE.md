# FRIDAY AI Assistant — Trigger Conflict Engine

## 1. The Tie-Breaking Hierarchy

### 1.1 The Danger of Aggressive State-Based Routing
In early system designs, state-based overrides operated as aggressive hard filters. When the assistant entered `TASK_MODE` (e.g., during active coding or debugging), the routing system biased heavily toward system applications, command executions, and file operations. Conversely, when in `CASUAL_CHAT` mode, the system assumed conversational fallbacks.

This created brittle failure modes. For instance, if a developer is in the middle of debugging a script (system state: `TASK_MODE`) and asks a conceptual question like *"Explain recursion"*, the aggressive state filter would incorrectly favor system action (such as searching files or opening an app) rather than delivering a cognitive explanation. 

### 1.2 Revised Tie-Breaking Hierarchy (State as Last Resort)
To ensure assistant state never overrides user intent, we redefine the tie-breaker hierarchy. Under the new engine, state context is treated as a weak prior—a fractional influence of last resort—while semantic intent and structural syntax dominate.

When two triggers $T_1$ and $T_2$ have overlapping or close scores ($\left| S(T_1) - S(T_2) \right| < \epsilon$), the conflict is resolved by evaluating a strict hierarchical pipeline:

```mermaid
graph TD
    A[Conflict Detected: Score Difference < epsilon] --> B{1. Intent Confidence}
    B -- Significant Difference? -->|Yes| C[Route to Higher Intent]
    B -- Tie? --> D{2. Dependency Parse Confidence}
    D -- Significant Difference? -->|Yes| E[Route to Structurally Aligned Trigger]
    D -- Tie? --> F{3. Object Resolution Grounding}
    F -- Local vs Remote Match? -->|Yes| G[Route to Grounded Target]
    F -- Tie? --> H{4. Trigger Reliability}
    H -- Different Reliability? -->|Yes| I[Route to Highly Reliable Trigger]
    H -- Tie? --> J{5. State Context Prior}
    J --> K[Resolve with State Prior Bias]
```

---

## 2. Confidence Weighting & Mathematical Fusion Mechanics

The conflict engine resolves competing triggers by calculating a high-resolution **Fused Conflict Score** ($S_{\text{conflict}}$) using a weighted linear combination of five distinct confidence dimensions:

$$S_{\text{conflict}}(T) = w_1 \cdot C_{\text{semantic}}(T) + w_2 \cdot C_{\text{dependency}}(T) + w_3 \cdot C_{\text{grounding}}(T) + w_4 \cdot R_{\text{trigger}}(T) + w_5 \cdot \Psi_{\text{state}}(T \mid S)$$

Under the strict operational constraint:
$$\sum_{i=1}^{5} w_i = 1.0$$

The calibrated weights are configured as follows:

| Weight | Dimension | Baseline Coefficient | Operational Rationale |
| :--- | :--- | :--- | :--- |
| $w_1$ | **Semantic Intent Confidence** | $0.45$ | Dominates routing; reflects pure NLU probability. |
| $w_2$ | **Dependency Parse Confidence** | $0.25$ | Grammatical structure and object-verb alignment. |
| $w_3$ | **Object Resolution Grounding** | $0.15$ | Entity matching (e.g. app installed, URL reachable). |
| $w_4$ | **Trigger Reliability** | $0.10$ | Historical trust and learned success rates. |
| $w_5$ | **State Context Prior** | $0.05$ | Weak bias; only acts as a tie-breaker of last resort. |

### 2.2 Formulation of the State Context Prior: $\Psi_{\text{state}}(T \mid S)$
The state prior $\Psi_{\text{state}}(T \mid S) \in [0, 1]$ represents the weak probability modifier for trigger $T$ given the active assistant state $S \in \{\text{TASK\_MODE}, \text{CASUAL\_CHAT}, \text{MEDIA\_MODE}\}$:

$$\Psi_{\text{state}}(T \mid S) = \text{softmax} \left( M_{S, T} \right)$$
Where $M$ is a static state-trigger association matrix:

```
                  TASK_MODE    CASUAL_CHAT    MEDIA_MODE
SYSTEM_STATUS  [    0.85,         0.10,          0.20    ]
NATIVE_OS      [    0.90,         0.05,          0.15    ]
MEDIA_PLAY     [    0.10,         0.20,          0.90    ]
AI_QUERY       [    0.40,         0.90,          0.20    ]
```

Because $w_5 = 0.05$, the maximum absolute score contribution of the state prior is bounded by $0.05$. Thus, a semantic score difference of even $0.06$ in favor of a cognitive explanation will easily override a system action bias in `TASK_MODE`.

---

## 3. Syntactic Dependency Parsing Strategy

To distinguish between highly overlapping queries, the conflict engine executes a **Syntactic Dependency Parser** that evaluates the grammar tree of the user request.

### 3.1 Resolving "Explain Rust" vs. "Play Rust tutorial"
Let us analyze the grammatical dependency structure of the two queries:

#### Case A: "Explain Rust"
* **Syntactic Structure**: Verb + Direct Object
* **Dependency Tree**:
  - `Explain` (ROOT, Part-Of-Speech: VERB)
  - `Rust` (dobj, Part-Of-Speech: PROPN)
* **Parser Action**: The verb `Explain` maps strictly to `EXPLANATION` semantic schemas. The noun `Rust` is classified as a topic. The dependency match score for cognitive `AI_QUERY` is $1.0$.

#### Case B: "Play Rust tutorial"
* **Syntactic Structure**: Verb + Direct Object Noun Phrase + Modifier
* **Dependency Tree**:
  - `Play` (ROOT, Part-Of-Speech: VERB)
  - `tutorial` (dobj, Part-Of-Speech: NOUN)
  - `Rust` (compound/noun adjunct, Part-Of-Speech: PROPN)
* **Parser Action**: The root verb `Play` maps strictly to `EXECUTION` / `MEDIA` schemas. The direct object `tutorial` indicates educational media content. `Rust` acts as a search modifier for the media search query. The dependency match score for `MEDIA_PLAY` is $1.0$, while the score for cognitive `AI_QUERY` is dropped to $0.15$ since `Play` is not an explanatory verb.

### 3.2 Grammatical Extraction Logic
The parsing strategy is implemented using a lightweight, rules-based syntactic scanner inside `brain/planner.py`:
1. **Verb Extraction**: Identify the ROOT verb of the query.
2. **Verb Class Mapping**: Map the ROOT verb to its core behavioral class:
   - *Explanatory Verbs* (`explain`, `what is`, `how do`, `define`, `understand`) $\rightarrow$ Cognitive bias.
   - *Action/Command Verbs* (`open`, `launch`, `play`, `start`, `close`, `minimize`) $\rightarrow$ OS/Media bias.
3. **Object Extraction**: Identify the direct object (`dobj`) and nominal subjects (`nsubj`).
4. **Target Feasibility Check**: Check if the direct object is an executable binary or local resource.

---

## 4. Conflict Resolution Walkthrough

Let us inspect how the Conflict Engine handles a real-world tie-breaking scenario.

### Scenario: User is in `TASK_MODE` (debugging) and queries: *"Explain recursion"*
* **Traditional Failure**: System detects `TASK_MODE`, maps `"recursion"` to a potential file/module or runs an OS script, or triggers a low-confidence warning due to state mismatch.
* **New Conflict Engine Resolution**:
  1. **Scores Calculation**:
     - **T1: AI_QUERY (Cognitive)**
       - $C_{\text{semantic}} = 0.95$ (Strong semantic mapping to coding explanation)
       - $C_{\text{dependency}} = 0.98$ (Root verb `Explain` maps perfectly to explanation)
       - $C_{\text{grounding}} = 0.50$ (No local binary named "recursion")
       - $R_{\text{trigger}} = 0.96$
       - $\Psi_{\text{state}} = 0.40$ (Low prior for cognitive tasks in TASK_MODE)
       - **Unified Score ($T_1$)**:
         $$S(T_1) = (0.45 \times 0.95) + (0.25 \times 0.98) + (0.15 \times 0.50) + (0.10 \times 0.96) + (0.05 \times 0.40) = 0.8635$$
     - **T2: NATIVE_OS (System Command / File Search)**
       - $C_{\text{semantic}} = 0.40$ (Weak semantic match)
       - $C_{\text{dependency}} = 0.10$ (Grammar doesn't map to system command)
       - $C_{\text{grounding}} = 0.20$ (No local file named "recursion" exists on the path)
       - $R_{\text{trigger}} = 0.90$
       - $\Psi_{\text{state}} = 0.90$ (High prior for system actions in TASK_MODE)
       - **Unified Score ($T_2$)**:
         $$S(T_2) = (0.45 \times 0.40) + (0.25 \times 0.10) + (0.15 \times 0.20) + (0.10 \times 0.90) + (0.05 \times 0.90) = 0.3700$$
  2. **Decision**: $S(T_1) = 0.8635$ vs $S(T_2) = 0.3700$. Even with a massive state bias in favor of `NATIVE_OS` ($0.90$ vs $0.40$), the cognitive explanation wins by a margin of $0.4935$ because semantic intent and syntactic structure dominate the routing pipeline.

---

## 5. Conflict Engine Validation Suite

To verify the correct operational boundaries of the conflict engine, the following automated test assertions are integrated:

```python
# test_conflict_engine.py
import pytest
from brain.planner import PlannerBrain
from brain.context_manager import SystemState

@pytest.mark.parametrize(
    "query, active_state, expected_brain",
    [
        # Cognitive queries must always win even during TASK_MODE
        ("Explain recursion", "TASK_MODE", "LLM"),
        ("What is photosynthesis", "TASK_MODE", "LLM"),
        ("How does a vector search work", "TASK_MODE", "LLM"),
        
        # Command queries must win even during CASUAL_CHAT
        ("Open notepad", "CASUAL_CHAT", "NATIVE_OS"),
        ("Play some lofi music", "CASUAL_CHAT", "MEDIA"),
        ("Take a screenshot", "CASUAL_CHAT", "NATIVE_OS"),
        
        # Syntactic disambiguation checks
        ("Explain Rust", "TASK_MODE", "LLM"),
        ("Play Rust tutorial", "TASK_MODE", "MEDIA"),
    ]
)
def test_conflict_resolution_matrix(query, active_state, expected_brain):
    planner = PlannerBrain()
    # Force system state prior to simulate target environment
    planner.set_simulated_state(active_state)
    
    decision = planner.plan(query)
    assert decision.target_brain == expected_brain, \
        f"Failed routing '{query}' in state '{active_state}'. Expected {expected_brain}, got {decision.target_brain}"
```

This structural validation suite ensures that the system handles edge cases gracefully, preventing aggressive state-based tie-breakers from corrupting the user's intent.
