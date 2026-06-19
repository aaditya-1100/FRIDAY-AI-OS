import asyncio
import os
from typing import Dict, Any
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.security.permission_engine import permission_engine
from duckduckgo_search import DDGS

class WebAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.WEB_AGENT)

    async def startup(self) -> None:
        logger.info("[WebAgent] Startup complete (Running in zero-browser API-only search mode).")

    async def shutdown(self) -> None:
        logger.info("[WebAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return ["WEB_SEARCH", "SEARCH"]

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.parameters.get("intent") or dispatch.intent
        query = dispatch.parameters.get("query", "")
        
        # 1. Whitelist guard
        if intent not in {"WEB_SEARCH", "SEARCH"}:
            logger.warning(f"[WebAgent] Rejected architecture-violating intent: {intent}")
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": "intent not handled by web_agent"},
                correlation_id=dispatch.correlation_id
            )
        
        # 2. Permission check
        allowed = await permission_engine.check_permission(
            agent_trust_level=self.trust_level,
            tool_name=intent,
            agent_id=self.agent_id,
            correlation_id=dispatch.correlation_id,
            session_id=dispatch.session_id
        )
        if not allowed:
            logger.warning(f"[WebAgent] Permission denied for intent: {intent}")
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": "Permission denied"},
                correlation_id=dispatch.correlation_id
            )

        try:
            logger.info(f"[WebAgent] Executing API search for query: '{query}'")
            serper_key = os.environ.get("SERPER_API_KEY")
            serper_success = False
            results = []
            
            if serper_key:
                try:
                    logger.info("[WebAgent] Calling Serper search API...")
                    import httpx
                    headers = {
                        "X-API-KEY": serper_key,
                        "Content-Type": "application/json"
                    }
                    async with httpx.AsyncClient() as client:
                        r = await client.post("https://google.serper.dev/search", json={"q": query}, headers=headers, timeout=5.0)
                        r.raise_for_status()
                        data = r.json()
                        for item in data.get("organic", [])[:5]:
                            results.append({
                                "title": item.get("title", ""),
                                "url": item.get("link", ""),
                                "snippet": item.get("snippet", "")
                            })
                        serper_success = True
                except Exception as e:
                    logger.warning(f"[WebAgent] Serper API search failed: {e}. Falling back to DuckDuckGo...")
                    
            if not serper_key or not serper_success:
                logger.info("[WebAgent] Using DuckDuckGo fallback...")
                
                def _ddg_search(q):
                    with DDGS() as ddgs:
                        return list(ddgs.text(q, max_results=5))

                loop = asyncio.get_running_loop()
                raw_results = await loop.run_in_executor(None, _ddg_search, query)
                results = []
                for item in raw_results:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "snippet": item.get("body", "")
                    })

            # Check if empty results
            if not results:
                logger.warning(f"[WebAgent] Search returned empty results list (query: '{query}').")
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.FAILED,
                    payload={"reason": "no_results"},
                    correlation_id=dispatch.correlation_id
                )

            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.SUCCESS,
                payload={"results": results},
                correlation_id=dispatch.correlation_id
            )
            
        except Exception as e:
            logger.error(f"[WebAgent] Error in handle_task: {e}", exc_info=True)
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": str(e)},
                correlation_id=dispatch.correlation_id
            )
