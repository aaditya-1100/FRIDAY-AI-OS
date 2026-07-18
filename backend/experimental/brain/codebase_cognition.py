"""
brain/codebase_cognition.py — AST Codebase Parser & Architecture Semantic Retrieval Engine.
Parses backend files recursively, extracts functions/classes/docstrings, caches to data/codebase_map.json,
and performs targeted keyword-relevance retrieval to serve self-architecture queries under 5ms.
"""
import ast
import json
import os
import re
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
MAP_FILE = BACKEND_DIR / "data" / "codebase_map.json"

# Static, highly refined high-level architectural summaries for conceptual alignment
_CORE_CONCEPTUAL_SUMMARIES = {
    "architecture": (
        "FRIDAY operates as a persistent, low-entropy real-time cognitive OS companion. "
        "The architecture is divided into three tiers: (1) Cognitive & Contextual Tier (brain/planner.py, "
        "brain/intent_parser.py, brain/context_manager.py, brain/identity_manager.py) which handles rule-based routing, "
        "LLM intent resolution, dynamic multi-turn pronoun tracking, and contextual identity slicing; "
        "(2) Execution & Retrieval Tier (execution/action_executor.py, system/live_data.py, system/temporal_engine.py) "
        "which runs parallel live web searches with circuit breakers, coordinates system applications, and schedules background "
        "reminders/timers; (3) Voice & Socket Runtime Tier (voice/listen.py, voice/speak.py, api/server.py) which handles "
        "persistent microphone capturing, adaptive pacing turn-taking,Edge-TTS voice synthesis, and low-latency WebSocket sync."
    ),
    "retrieval": (
        "Real-time search and retrieval is handled in system/live_data.py via the `realtime_web_query()` function. "
        "It uses a concurrent ThreadPoolExecutor to query multiple search sources in parallel (Serper Google, "
        "Tavily API, DuckDuckGo News/Text/Instant, and Google RSS). It implements circuit breakers and a "
        "self-healing fallback rewriter. Google RSS acts as the robust last-resort fallback. Synthesis is governed by "
        "strict Google AI Overview guidelines, forcing responses to be highly grounded, factual, and under 60 words."
    ),
    "spotify": (
        "Spotify integration is located in system/spotify_client.py (OAuth PKCE login, token caching) and system/spotify_control.py "
        "which provides play/pause, volume, skip, queue, and playback state controls. Media routing is handled inside "
        "execution/action_executor.py, which evaluates local Spotify app availability, web APIs, and falls back to YouTube search scrape "
        "on failure to guarantee music delivery."
    ),
    "temporal": (
        "Temporal systems (reminders, timers, alarms, stopwatches) are coordinated by system/temporal_engine.py. "
        "It parses relative and absolute expressions (e.g. 'in 5 minutes', 'every day at 9 AM') using regular expressions, "
        "maintains active items in an auto-initialized data/temporal_state.json, and runs a thread-safe scheduler background tick "
        "registered inside api/server.py lifespan. Alerts trigger non-blocking spoken announcements and visual orb state sync."
    ),
    "voice": (
        "Voice interaction is implemented in voice/listen.py and voice/speak.py. "
        "voice/listen.py uses a global persistent ResilientMicrophone stream context to bypass Windows PortAudio opening latencies, "
        "and runs `_adaptive_listen()`—a dynamic chunk-by-chunk silence pacing machine. Silence timeouts scale dynamically: "
        "TASK_MODE gets rapid cutoff (0.6s), while CASUAL_CHAT storytelling gets generous cushions (2.3s) to tolerate hesitations. "
        "voice/speak.py uses Edge-TTS, gTTS, and SAPI5 pyttsx3 fallbacks, supporting base64 WebSocket and local pygame play."
    ),
    "memory": (
        "Memory consists of ShortTermMemory (memory/short_term.py -Cap-12 rolling conversational turns), PreferenceMemory "
        "(memory/preference.py -Favorite app and city parameters), SemanticMemory (memory/semantic.py -Relational facts), "
        "and EpisodicMemory (memory/episodic.py -Recent successful execution events). ShortTermMemory implements Dynamic "
        "Context Compression: when turns exceed 12, older turns are asynchronously summarized and appended to a running summary, "
        "keeping prompt contexts small while retaining multi-hour dialogue continuity."
    ),
    "websocket": (
        "The real-time synchronization is run via FastAPI WebSockets in api/server.py at `/api/ws`. "
        "It broadcasts states (IDLE, LISTENING, THINKING, SPEAKING) registered via core/state_manager.py, transmits base64 synthesized "
        "audio streams, and processes user text commands. It is protected by core/runtime_stability.py which runs a "
        "janitor cleanup loop every 5 minutes to prune dead WebSocket connections, cancel orphaned async tasks, and quit idle pygame mixer mixers."
    ),
    "state": (
        "Conversational states are managed by core/state_manager.py. Heuristics inside core/pipeline.py dynamically transition "
        "the conversational mode between CASUAL_CHAT, TASK_MODE, RETRIEVAL_MODE, and EMOTIONAL_CONTEXT. These states adjust "
        "listening silence timeouts, LLM synthesis prompt parameters, and visual orb color animations on the React frontend."
    )
}


class CodebaseStructureParser:
    """AST-based parser that indexes Python modules, classes, functions, and imports in backend."""
    
    @staticmethod
    def parse_file(file_path: Path) -> dict:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()
            
            tree = ast.parse(source, filename=str(file_path))
            
            module_doc = ast.get_docstring(tree) or ""
            classes = []
            functions = []
            imports = []
            
            for node in ast.iter_child_nodes(tree):
                # Extract Imports
                if isinstance(node, ast.Import):
                    for name in node.names:
                        imports.append(name.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
                
                # Extract standalone functions
                elif isinstance(node, ast.FunctionDef):
                    doc = ast.get_docstring(node) or ""
                    args = [arg.arg for arg in node.args.args]
                    functions.append({
                        "name": node.name,
                        "doc": doc.strip().split("\n")[0] if doc else "",
                        "args": args
                    })
                
                # Extract classes
                elif isinstance(node, ast.ClassDef):
                    class_doc = ast.get_docstring(node) or ""
                    methods = []
                    for child in ast.iter_child_nodes(node):
                        if isinstance(child, ast.FunctionDef):
                            child_doc = ast.get_docstring(child) or ""
                            c_args = [arg.arg for arg in child.args.args]
                            methods.append({
                                "name": child.name,
                                "doc": child_doc.strip().split("\n")[0] if child_doc else "",
                                "args": c_args
                            })
                    classes.append({
                        "name": node.name,
                        "doc": class_doc.strip().split("\n")[0] if class_doc else "",
                        "methods": methods
                    })
            
            return {
                "doc": module_doc.strip().split("\n")[0] if module_doc else "",
                "classes": classes,
                "functions": functions,
                "imports": imports,
                "lines": len(source.splitlines()),
                "size_bytes": len(source.encode("utf-8"))
            }
        except Exception as e:
            return {"error": str(e)}

    @classmethod
    def index_all(cls) -> dict:
        """Scan backend directory recursively and build the indexed structure."""
        print("[CODEBASE INDEXER] Scanning backend modules...")
        index = {}
        for root, _, files in os.walk(BACKEND_DIR):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(BACKEND_DIR).as_posix()
                    file_info = cls.parse_file(full_path)
                    if "error" not in file_info:
                        index[rel_path] = file_info
        print(f"[CODEBASE INDEXER] Indexed {len(index)} modules successfully.")
        return index


class CodebaseRetrievalLayer:
    """Retrieves targeted conceptual summaries and exact module AST signatures for queries."""
    
    def __init__(self):
        self._map_data = None
        self._load_map()

    def _load_map(self):
        """Loads codebase map from JSON cache or builds it on demand."""
        try:
            if MAP_FILE.exists():
                with open(MAP_FILE, "r", encoding="utf-8") as f:
                    self._map_data = json.load(f)
            else:
                self._map_data = CodebaseStructureParser.index_all()
                # Ensure data dir exists
                MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(MAP_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._map_data, f, indent=2)
        except Exception as e:
            print(f"[CODEBASE ERROR] Failed loading or parsing codebase map: {e}")
            self._map_data = {}

    def rebuild_index(self):
        """Force rebuild AST cache."""
        self._map_data = CodebaseStructureParser.index_all()
        try:
            MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(MAP_FILE, "w", encoding="utf-8") as f:
                json.dump(self._map_data, f, indent=2)
        except Exception as e:
            print(f"[CODEBASE ERROR] Failed caching rebuilt index: {e}")

    def retrieve_context(self, query: str) -> str:
        """Evaluate query keyword relevance, retrieve static overview, and append specific AST definitions."""
        q = query.lower().strip()
        
        # 1. Match high-level conceptual summary
        summary_key = "architecture"
        if any(w in q for w in ("search", "retrieval", "tavily", "serper", "rss", "web")):
            summary_key = "retrieval"
        elif any(w in q for w in ("spotify", "music", "play", "song", "audio")):
            summary_key = "spotify"
        elif any(w in q for w in ("remind", "timer", "alarm", "stopwatch", "schedule", "temporal")):
            summary_key = "temporal"
        elif any(w in q for w in ("voice", "speak", "listen", "mic", "microphone", "sound", "pacing", "turn-taking")):
            summary_key = "voice"
        elif any(w in q for w in ("memory", "short", "preference", "episodic", "semantic", "continuity", "compress")):
            summary_key = "memory"
        elif any(w in q for w in ("websocket", "ws", "socket", "client", "cleanup", "janitor")):
            summary_key = "websocket"
        elif any(w in q for w in ("state", "idle", "thinking", "executing", "conversational")):
            summary_key = "state"
            
        conceptual_block = f"Core Concept:\n{_CORE_CONCEPTUAL_SUMMARIES[summary_key]}"
        
        # 2. Match specific files to display AST interfaces (classes/methods)
        matched_files = []
        if summary_key == "retrieval":
            matched_files = ["system/live_data.py"]
        elif summary_key == "spotify":
            matched_files = ["system/spotify_control.py", "system/spotify_client.py"]
        elif summary_key == "temporal":
            matched_files = ["system/temporal_engine.py"]
        elif summary_key == "voice":
            matched_files = ["voice/listen.py", "voice/speak.py"]
        elif summary_key == "memory":
            matched_files = ["memory/short_term.py", "brain/context_manager.py"]
        elif summary_key == "websocket":
            matched_files = ["api/server.py", "core/runtime_stability.py"]
        elif summary_key == "state":
            matched_files = ["core/state_manager.py", "core/pipeline.py"]
        else:
            # General overview, match planner
            matched_files = ["brain/planner.py", "brain/intent_parser.py"]
            
        ast_block = "\n\nRelevant Module Interface Signatures:"
        for f in matched_files:
            if f in self._map_data:
                f_data = self._map_data[f]
                ast_block += f"\n- file://backend/{f} ({f_data.get('lines', 0)} lines):"
                if f_data.get("classes"):
                    for c in f_data["classes"]:
                        methods_str = ", ".join([f"{m['name']}({', '.join(m['args'])})" for m in c.get("methods", [])])
                        ast_block += f"\n  * class {c['name']} -> Methods: [{methods_str}]"
                if f_data.get("functions"):
                    funcs_str = ", ".join([f"{fn['name']}({', '.join(fn['args'])})" for fn in f_data["functions"][:5]])
                    ast_block += f"\n  * functions -> [{funcs_str}]"
                    
        return f"{conceptual_block}\n{ast_block}"
