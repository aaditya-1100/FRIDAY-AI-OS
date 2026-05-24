import os

from pathlib import Path

from groq import Groq

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

ENV_PATH = BASE_DIR / ".env"

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
You are FRIDAY, a futuristic AI personal assistant — intelligent, direct, and concise.

Rules:
- Respond naturally in 1-3 sentences unless detail is required
- Be confident and precise — never vague
- Use casual professional tone (like a brilliant colleague)
- If asked about current events/dates/scores, be honest about knowledge limits
- Never say "As an AI" — just answer
- Never pad responses with filler phrases
"""


DEFAULT_MODEL      = "llama-3.1-8b-instant"     # fast, low-latency for responses
INTENT_MODEL       = "llama-3.3-70b-versatile"  # smarter, used for intent parsing
REALTIME_MODEL     = "llama-3.3-70b-versatile"  # used for realtime summarization


def ask_groq(query: str, system_prompt=None, model: str | None = None, history: list | None = None) -> str:
    c = get_groq_client()
    if c is None:
        print("[GROQ] GROQ_API_KEY not set — configure backend/.env")
        return "I am sorry sir, but my Groq API key is not configured. Please check the environment variables."

    try:
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

        try:
            response = c.chat.completions.create(
                model=chosen_model,
                temperature=0.25,
                timeout=45.0,
                messages=messages,
            )
            return response.choices[0].message.content
        except Exception as e:
            # Automatic failover retry if primary versatile model fails
            if chosen_model == "llama-3.3-70b-versatile":
                print(f"[GROQ FAILOVER] Model {chosen_model} failed due to rate limits or errors. Retrying with llama-3.1-8b-instant...")
                try:
                    response = c.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        temperature=0.25,
                        timeout=30.0,
                        messages=messages,
                    )
                    return response.choices[0].message.content
                except Exception as failover_err:
                    print(f"[GROQ FAILOVER ERROR] Failover failed: {failover_err}")
                    raise failover_err
            raise e

    except Exception as e:
        print(f"[GROQ ERROR] {e}")
        if "401" in str(e) or "invalid_api_key" in str(e).lower() or "authentication" in str(e).lower():
            return "I am sorry sir, but my Groq API key is invalid. Please check the configuration."
        return "I am sorry sir, I encountered an error connecting to my brain."
