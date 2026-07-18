import asyncio
import functools
import os
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.security.permission_engine import permission_engine
from duckduckgo_search import DDGS


class WebAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.WEB_AGENT)

    async def startup(self) -> None:
        logger.info("[WebAgent] Startup complete.")

    async def shutdown(self) -> None:
        logger.info("[WebAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return ["WEB_SEARCH", "SEARCH", "WEATHER", "NEWS", "REALTIME_QUERY"]

    def _ok(self, dispatch, payload):
        return TaskResult(
            task_id=dispatch.task_id,
            agent_id=self.agent_id,
            status=TaskStatus.SUCCESS,
            payload=payload,
            correlation_id=dispatch.correlation_id
        )

    def _fail(self, dispatch, error: str):
        return TaskResult(
            task_id=dispatch.task_id,
            agent_id=self.agent_id,
            status=TaskStatus.FAILED,
            payload={"error": error},
            correlation_id=dispatch.correlation_id
        )

    async def _tavily_search(self, query: str) -> list[dict]:
        """Primary search via Tavily API."""
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if not tavily_key:
            raise RuntimeError("TAVILY_API_KEY not set in environment")
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": 5},
                timeout=10.0
            )
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", "")
                }
                for item in data.get("results", [])
            ]

    async def _ddg_fallback(self, query: str) -> list[dict]:
        """Fallback search via DuckDuckGo."""
        def _sync_search(q):
            with DDGS() as ddgs:
                return list(ddgs.text(q, max_results=5))
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, _sync_search, query)
        return [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in raw
        ]

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        parameters = dispatch.parameters or {}

        allowed = await permission_engine.check_permission(
            agent_trust_level=self.trust_level,
            tool_name=intent,
            agent_id=self.agent_id,
            correlation_id=dispatch.correlation_id,
            session_id=dispatch.session_id
        )
        if not allowed:
            logger.warning(f"[WebAgent] Permission denied for intent: {intent}")
            return self._fail(dispatch, "Permission denied")

        try:
            # ── WEB_SEARCH / SEARCH ───────────────────────────────────────────
            if intent in ("WEB_SEARCH", "SEARCH"):
                query = parameters.get("query", "")
                logger.info(f"[WebAgent] Searching (Tavily primary): '{query}'")
                try:
                    results = await self._tavily_search(query)
                except Exception as e:
                    logger.warning(f"[WebAgent] Tavily failed: {e} — falling back to DuckDuckGo")
                    results = await self._ddg_fallback(query)
                if not results:
                    return self._fail(dispatch, "no_results")
                return self._ok(dispatch, {"results": results})

            # ── WEATHER ───────────────────────────────────────────────────────
            elif intent == "WEATHER":
                location = parameters.get("location") or ""
                query = parameters.get("query") or ""
                if not location:
                    from friday.memory.preference import PreferenceMemory
                    location = PreferenceMemory().get("default_city", "Kashipur, Uttarakhand, India")
                from system.live_data import get_weather
                loop = asyncio.get_running_loop()
                try:
                    summary = await asyncio.wait_for(
                        loop.run_in_executor(None, functools.partial(get_weather, location, query)),
                        timeout=20.0
                    )
                except asyncio.TimeoutError:
                    summary = "I am sorry sir, but the weather service timed out. Please try again."
                return self._ok(dispatch, {"response": summary})

            # ── NEWS ──────────────────────────────────────────────────────────
            elif intent == "NEWS":
                topic = parameters.get("topic") or ""
                from system.live_data import get_news
                loop = asyncio.get_running_loop()
                try:
                    summary = await asyncio.wait_for(
                        loop.run_in_executor(None, functools.partial(get_news, topic)),
                        timeout=20.0
                    )
                except asyncio.TimeoutError:
                    summary = "I am sorry sir, but the news service timed out. Please try again."
                return self._ok(dispatch, {"response": summary})

            # ── REALTIME_QUERY ────────────────────────────────────────────────
            elif intent == "REALTIME_QUERY":
                query = parameters.get("query", "")
                from friday.core.context_manager import context_manager
                mem_ctx_dict = context_manager.get_retrieval_context()
                memory_context = mem_ctx_dict.get("conversation_summary", "")
                from system.live_data import realtime_web_query
                loop = asyncio.get_running_loop()
                try:
                    summary = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, functools.partial(realtime_web_query, query, memory_context)
                        ),
                        timeout=25.0
                    )
                except asyncio.TimeoutError:
                    summary = "I am sorry sir, but the real-time search query timed out. Please try again."
                return self._ok(dispatch, {"response": summary})

            else:
                logger.warning(f"[WebAgent] Unhandled intent: {intent}")
                return self._fail(dispatch, f"WebAgent does not handle intent: {intent}")

        except Exception as e:
            logger.error(f"[WebAgent] Error in handle_task: {e}", exc_info=True)
            return self._fail(dispatch, str(e))
