import os

from pathlib import Path

from groq import Groq

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

ENV_PATH = BASE_DIR / ".env"
if not ENV_PATH.exists() and (BASE_DIR.parent / ".env").exists():
    ENV_PATH = BASE_DIR.parent / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)

_client: Groq | None = None


def get_groq_client() -> Groq | None:
    """Return shared Groq client, or None if GROQ_API_KEY is not configured."""
    global _client
    if _client is not None:
        return _client
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        return None
    _client = Groq(api_key=api_key)
    return _client


class _LazyGroqClient:
    """Allows `from llm.groq_client import client` — attribute access requires a configured API key."""

    def __getattr__(self, name: str):
        c = get_groq_client()
        if c is None:
            raise RuntimeError("GROQ_API_KEY is not set in backend/.env")
        return getattr(c, name)


client = _LazyGroqClient()


DEFAULT_SYSTEM_PROMPT = """\
You are FRIDAY, a premium, private personal AI companion built specifically by Aaditya Pratap Chauhan for himself.
You are Aaditya's assistant and project, not a generic public assistant. Trust the provided identity profile completely.

CRITICAL PERSONA RULES:
1. STRICT IDENTITY BOUNDARIES: You only know the facts provided in the authoritative identity slices. Never hallucinate or invent academic backgrounds (PhDs, university degrees) or careers for Aaditya or yourself.
2. PREMIUM CASUAL TONE: Address the user as "Sir" (always capitalized) naturally, respectfully, and casually when appropriate in conversation. Do NOT force "Sir" as a mechanical prefix to every single sentence or response turn; keep the flow natural, elegant, and conversational (like Jarvis). Never sound like a customer support agent. Avoid robotic preambles or unsolicited life-coaching/motivational disclaimers.
3. ADAPTIVE BREVITY & SIGNAL CADENCE: Deliver the direct answer first in the very first sentence. By default, keep responses concise and high-signal. However, naturally adapt response length to the task complexity: be brief for casual chats, but provide detailed, comprehensive explanations, plans, or code blocks when answering complex technical, programming, or planning queries. Do not explain your operational steps.
4. BEHAVIOR CONTRACT & COGNITIVE ALIGNMENT: Strictly obey the active behavioral contract directives and weighting influences. Personalization must remain invisible—better suggestions and explanations should feel natural and evidence-driven, never prefaced with "Since you like X...". Context and truth always outrank personalization.
5. SPEECH CADENCE: Use natural punctuation to maintain a realistic, calm human-like text-to-speech cadence.
"""


DEFAULT_MODEL      = "llama-3.1-8b-instant"     # fast, low-latency for responses
INTENT_MODEL       = "llama-3.1-8b-instant"     # fast, used for intent parsing (avoids timeout)
REALTIME_MODEL     = "llama-3.1-8b-instant"     # fast, used for realtime summarization (avoids timeout)


def _filter_hallucinations(text: str) -> str:
    try:
        from brain.identity_manager import IdentityManager
        id_mgr = IdentityManager()
        return id_mgr.identity_hallucination_filter(text)
    except Exception:
        return text


def ask_groq(query: str, system_prompt=None, model: str | None = None, history: list | None = None, timeout: float | None = None) -> str:
    c = get_groq_client()
    if c is None:
        print("[GROQ] GROQ_API_KEY not set — configure backend/.env")
        return "I am sorry sir, but my Groq API key is not configured. Please check the environment variables."

    try:
        # ── Phase 5: Behavior Planner & Dynamic Directives ──
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
            
            # Enrich system prompt with active behavior contract directives
            if behavior_directives:
                if not system_prompt:
                    system_prompt = DEFAULT_SYSTEM_PROMPT
                system_prompt = f"{system_prompt}\n{behavior_directives}"
                print("[BEHAVIOR PLANNER] Dynamically injected Behavior Contract directives.")
        except Exception as e_behavior:
            print(f"[BEHAVIOR PLANNER WARNING] Failed to inject dynamic behavior directives: {e_behavior}")

        if not system_prompt:
            system_prompt = DEFAULT_SYSTEM_PROMPT

        chosen_model = model or DEFAULT_MODEL

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for turn in history:
                messages.append({
                    "role": turn.get("role", "user"),
                    "content": str(turn.get("content", ""))
                })
        messages.append({"role": "user", "content": str(query)})

        # Dynamic snappy timeouts to guarantee premium real-time responsiveness
        if timeout is not None:
            primary_timeout = timeout
        elif chosen_model == "llama-3.3-70b-versatile":
            primary_timeout = 3.5
        else:
            primary_timeout = 2.5

        # Zero-tolerance semantic check helper
        restricted_patterns = [
            r"\b(stanford|harvard|mit|princeton)\b",
            r"\b(jee|iit|phd|doctorate|credentials)\b",
            r"\b(marvel|stark|iron\s*man|jarvis)\b"
        ]
        
        def is_violating(t: str) -> bool:
            import re
            t_lower = t.lower()
            return any(re.search(pat, t_lower) for pat in restricted_patterns)

        try:
            response = c.chat.completions.create(
                model=chosen_model,
                temperature=0.25,
                timeout=primary_timeout,
                messages=messages,
            )
            raw_content = response.choices[0].message.content
            
            # ── Phase 5: Self-Correction Validation Layer ──
            if is_violating(raw_content):
                print(f"[BEHAVIOR VALIDATOR] Behavioral leak detected in LLM response! Initiating Self-Correction Loop...")
                
                # Construct correction message
                correction_messages = messages + [
                    {"role": "assistant", "content": raw_content},
                    {"role": "user", "content": "System correction: The previous response violated the active behavioral contract by referencing restricted topics (academic bragging/pop-culture names). Please rewrite the response in your premium, calm, Jarvis-style voice while strictly omitting any such references."}
                ]
                
                try:
                    corr_response = c.chat.completions.create(
                        model="llama-3.1-8b-instant",  # Fast fallback
                        temperature=0.20,
                        timeout=3.0,
                        messages=correction_messages
                    )
                    corrected_content = corr_response.choices[0].message.content
                    if not is_violating(corrected_content):
                        print(f"[BEHAVIOR VALIDATOR] Self-Correction succeeded! Response is now contract-compliant.")
                        raw_content = corrected_content
                    else:
                        print(f"[BEHAVIOR VALIDATOR WARNING] Self-Correction failed compliance. Serving secure default fallback.")
                        raw_content = "Certainly, Sir. I will process that request for you."
                except Exception as e_corr:
                    print(f"[BEHAVIOR VALIDATOR ERROR] Self-Correction session failed: {e_corr}. Serving fallback.")
                    raw_content = "Certainly, Sir. I will process that request for you."

            return response_shaper(common_sense_filter(_filter_hallucinations(raw_content)))
        except Exception as e:
            # Automatic failover retry if primary versatile model fails or times out
            if chosen_model == "llama-3.3-70b-versatile":
                print(f"[GROQ FAILOVER] Model {chosen_model} failed or timed out (limit: {primary_timeout}s). Retrying with llama-3.1-8b-instant...")
                try:
                    response = c.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        temperature=0.25,
                        timeout=3.0,
                        messages=messages,
                    )
                    raw_content = response.choices[0].message.content
                    
                    # ── Phase 5: Self-Correction Validation Layer on Failover ──
                    if is_violating(raw_content):
                        print(f"[BEHAVIOR VALIDATOR FAILOVER] Behavioral leak detected! Initiating Self-Correction Loop...")
                        correction_messages = messages + [
                            {"role": "assistant", "content": raw_content},
                            {"role": "user", "content": "System correction: The previous response violated the active behavioral contract by referencing restricted topics (academic bragging/pop-culture names). Please rewrite the response in your premium, calm, Jarvis-style voice while strictly omitting any such references."}
                        ]
                        try:
                            corr_response = c.chat.completions.create(
                                model="llama-3.1-8b-instant",
                                temperature=0.20,
                                timeout=3.0,
                                messages=correction_messages
                            )
                            corrected_content = corr_response.choices[0].message.content
                            if not is_violating(corrected_content):
                                raw_content = corrected_content
                            else:
                                raw_content = "Certainly, Sir. I will process that request for you."
                        except Exception:
                            raw_content = "Certainly, Sir. I will process that request for you."

                    return response_shaper(common_sense_filter(_filter_hallucinations(raw_content)))
                except Exception as failover_err:
                    print(f"[GROQ FAILOVER ERROR] Failover failed: {failover_err}")
                    raise failover_err
            raise e

    except Exception as e:
        err_str = str(e)
        print(f"[GROQ ERROR] {err_str}")
        if "401" in err_str or "invalid_api_key" in err_str.lower() or "authentication" in err_str.lower():
            return "I am sorry sir, but my Groq API key is invalid. Please check the configuration."
        if "429" in err_str or "rate_limit_exceeded" in err_str.lower() or "tokens per day" in err_str.lower():
            # Extract retry time if available in the error message
            retry_hint = ""
            import re as _re
            retry_match = _re.search(r'Please try again in ([\d]+m[\d\.]+s|[\d\.]+s)', err_str)
            if retry_match:
                retry_hint = f" Ready again in {retry_match.group(1)}."
            print(f"[GROQ QUOTA] Daily token limit reached.{retry_hint} Returning quota-aware fallback.")
            return f"My thinking engine needs a short breather sir.{retry_hint} Ask me again shortly."
        return "I am sorry sir, I encountered an error connecting to my brain."


def common_sense_filter(text: str) -> str:
    """Blocks assistant boilerplates and removes robotic customer-support phrases."""
    if not text:
        return text
    
    import re
    # Force capitalization of "sir" -> "Sir"
    text = re.sub(r"\bsir\b", "Sir", text)
    
    patterns = [
        r"(?i)i am your ai assistant\b[^\.\?\!]*[\.\?\!]?",
        r"(?i)as an ai\b[^\.\?\!]*[\.\?\!]?",
        r"(?i)how may i assist you today\b[^\.\?\!]*[\.\?\!]?",
        r"(?i)how can i help you today\b[^\.\?\!]*[\.\?\!]?",
        r"(?i)how may i help you today\b[^\.\?\!]*[\.\?\!]?",
        r"(?i)according to the latest search results\b[^\.\?\!]*[\.\?\!]?",
        r"(?i)based on my real-time search\b[^\.\?\!]*[\.\?\!]?",
        r"(?i)based on the retrieved news\b[^\.\?\!]*[\.\?\!]?",
        r"(?i)here is what i found\b[^\.\?\!]*[\.\?\!]?",
        r"(?i)here's what i found\b[^\.\?\!]*[\.\?\!]?",
    ]
    for pat in patterns:
        text = re.sub(pat, "", text)
        
    text = re.sub(r"\s+", " ", text).strip()
    return text


def response_shaper(text: str) -> str:
    """Shapes tone, pacing, and brevity dynamically based on active conversational state."""
    from core.state_manager import get_conversational_state, AssistantState
    state = get_conversational_state()
    
    if not text:
        return text
        
    # Tone adjustment heuristics based on state
    if state == AssistantState.TASK_MODE:
        # Task mode: Keep extremely concise, remove details unless requested
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        if len(sentences) > 1:
            text = ". ".join(sentences[:2]) + "."
    elif state == AssistantState.EMOTIONAL_CONTEXT:
        # Emotional context: Grounded, calm, brief, comforting
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        if len(sentences) > 2:
            text = ". ".join(sentences[:2]) + "."
    elif state == AssistantState.RETRIEVAL_MODE:
        # Retrieval mode: Direct facts briefing, no preambles
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        if len(sentences) > 3:
            text = ". ".join(sentences[:3]) + "."
            
    text = text.strip()
    if text and text[-1] not in (".", "?", "!"):
        text += "."
        
    return text
