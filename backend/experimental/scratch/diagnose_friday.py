import os
import sys
import json
import re

# Ensure backend imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from brain.planner import PlannerBrain
from brain.intent_parser import parse_intent, validate_intent_sanity
from brain.context_manager import ContextManager
from brain.identity_manager import IdentityManager
from memory.preference import PreferenceMemory
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory

planner = PlannerBrain()
context_mgr = ContextManager()
pref_mem = PreferenceMemory()
episodic_mem = EpisodicMemory()
semantic_mem = SemanticMemory()
id_mgr = IdentityManager()

TRIGGER_TEST_QUERIES = [
    "Explain Python",
    "Explain Rust",
    "Rust vs Python",
    "Play Rust tutorial",
    "Python tutorial",
    "Open Python documentation",
    "Compare Rust and Python"
]

out_lines = []

def log(msg):
    print(msg)
    out_lines.append(msg)

log("================================================================================")
log("              DIAGNOSTIC TEST 1: TRIGGER AUTHORITY FAILURE ANALYSIS")
log("================================================================================")

for q in TRIGGER_TEST_QUERIES:
    log(f"\nQUERY: \"{q}\"")
    dec = planner.plan(q, context_mgr, pref_mem, episodic_mem)
    log(f"[Planner] Winner Target Brain: {dec.target_brain}")
    log(f"[Planner] Freshness Score: {dec.freshness_score:.4f} | Signals: {dec.freshness_signals}")
    log(f"[Planner] Trigger Scores: {planner.trigger_scores}")
    log(f"[Planner] Tiebreak Invoked: {planner.is_tiebreak_invoked}")
    
    if "open" in q.lower():
        mock_parsed = {"intent": "OPEN", "target": q.lower().replace("open", "").strip()}
    elif "play" in q.lower():
        mock_parsed = {"intent": "PLAY_MEDIA", "query": q.lower().replace("play", "").strip()}
    else:
        mock_parsed = {"intent": "AI_QUERY", "query": q}
        
    log(f"[Intent Classifier Mock] Mock classified intent prior to sanity check: {mock_parsed}")
    sanity_out = validate_intent_sanity(mock_parsed, q)
    log(f"[Sanity Validation Layer] Final Resolved Intent: {sanity_out}")

log("\n================================================================================")
log("              DIAGNOSTIC TEST 2: MEMORY PARTICIPATION ANALYSIS")
log("================================================================================")

MEMORY_TEST_QUERIES = [
    ("Remember FRIDAY is my AI project", "What is my AI project?"),
    ("Remember I am building FRIDAY", "What am I building?"),
    ("Remember project status is implementation phase", "What is current project status?")
]

for write_q, read_q in MEMORY_TEST_QUERIES:
    log(f"\n--- Turn Pair ---")
    log(f"WRITE QUERY: \"{write_q}\"")
    
    dec_write = planner.plan(write_q, context_mgr, pref_mem, episodic_mem)
    log(f"  [Write Planner] Winner: {dec_write.target_brain}")
    
    mock_write = {"intent": "AI_QUERY", "query": write_q}
    sanity_write = validate_intent_sanity(mock_write, write_q)
    log(f"  [Write Sanity] Resolved Intent: {sanity_write.get('intent')}")
    
    log("  [Memory Check] Checking if semantic memory size changed or key is present...")
    
    log(f"READ QUERY: \"{read_q}\"")
    dec_read = planner.plan(read_q, context_mgr, pref_mem, episodic_mem)
    log(f"  [Read Planner] Winner: {dec_read.target_brain}")
    
    retrieved = context_mgr.enrich_query(read_q)
    log(f"  [Context enrichment] Original: \"{read_q}\" -> Enriched: \"{retrieved}\"")
    
    matched_facts = []
    q_low = read_q.lower()
    for k, v in semantic_mem.knowledge.items():
        if k in q_low:
            matched_facts.append((k, v))
    log(f"  [Semantic Memory Lookup] Matched facts in semantic.json: {matched_facts}")

log("\n================================================================================")
log("              DIAGNOSTIC TEST 3: IDENTITY PARTICIPATION ANALYSIS")
log("================================================================================")

query = "What project are we working on?"
log(f"QUERY: \"{query}\"")

try:
    from brain.identity_manager import IdentityManager
    id_mgr = IdentityManager()
    engine = id_mgr.engine
    intent_vector = engine.get_intent_vector(query)
    overrides = engine.detect_overrides(query)
    relevance_score = engine.get_relevance_score(query, intent_vector, overrides)
    influence_weight = engine.get_influence_weight(relevance_score, intent_vector)
    signals = engine.get_behavioral_signals(id_mgr.profile, intent_vector, overrides, relevance_score, influence_weight)
    behavior_directives = engine.compile_signals_directives(signals, overrides)
    
    log("\n--- IDENTITY MANAGER DYNAMICS ---")
    log(f"Relevance Score: {relevance_score}")
    log(f"Influence Weight: {influence_weight}")
    log(f"Behavior Directives injected into System Prompt:\n{behavior_directives}")
    
    slices = id_mgr.get_contextual_slices(query)
    log(f"\nTargeted Context Slices returned by get_contextual_slices(query):\n{json.dumps(slices, indent=2)}")
    
except Exception as e:
    log(f"Error simulating identity manager: {e}")

log("\n================================================================================")

out_path = os.path.join(os.path.dirname(__file__), "diagnose_out_utf8.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))
print(f"Diagnostics written successfully to: {out_path}")
