import asyncio
import os
from typing import Dict, Any
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.security.permission_engine import permission_engine
from browser.browser_agent import search_google, youtube_search
from duckduckgo_search import DDGS

SEARCH_INTENTS = {"WEB_SEARCH", "SEARCH"}
BROWSER_INTENTS = {"WEB_SCRAPE", "BROWSER_OPEN", "BROWSER_SEARCH", "BROWSER_FILL", "BROWSER_CLICK", "BROWSER_SCREENSHOT", "BROWSER_CLOSE"}

class WebAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.WEB_AGENT)
        self.playwright = None
        self.browser = None

    async def startup(self) -> None:
        logger.info("[WebAgent] Startup complete (Playwright will be initialized lazily).")

    async def _ensure_browser(self) -> None:
        if self.browser is None:
            logger.info("[WebAgent] Lazily initializing Playwright and browser...")
            try:
                from playwright.async_api import async_playwright
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(headless=True)
                logger.info("[WebAgent] Playwright initialized successfully.")
            except Exception as e:
                logger.error(f"[WebAgent] Playwright initialization failed: {e}")
                raise

    async def _ensure_page(self):
        if not self.browser:
            raise RuntimeError("Browser not initialized")
        contexts = self.browser.contexts
        if not contexts:
            context = await self.browser.new_context()
        else:
            context = contexts[0]
        pages = context.pages
        if not pages:
            page = await context.new_page()
        else:
            page = pages[0]
        return page

    async def shutdown(self) -> None:
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        logger.info("[WebAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return [
            "WEB_SEARCH",
            "WEB_SCRAPE",
            "BROWSER_OPEN",
            "BROWSER_SEARCH",
            "BROWSER_FILL",
            "BROWSER_CLICK",
            "BROWSER_SCREENSHOT",
            "BROWSER_CLOSE"
        ]

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.parameters.get("intent") or dispatch.intent
        query = dispatch.parameters.get("query", "")
        url = dispatch.parameters.get("url", "")
        
        # 1. Permission check
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

        BROWSER_AUTOMATION_INTENTS = {
            "BROWSER_OPEN", "BROWSER_SEARCH", "BROWSER_FILL",
            "BROWSER_CLICK", "BROWSER_SCREENSHOT", "BROWSER_CLOSE", "WEB_SCRAPE"
        }

        try:
            logger.info(f"[WebAgent] Handling intent: {intent}")
            
            if intent in BROWSER_AUTOMATION_INTENTS:
                try:
                    await self._ensure_browser()
                    page = await self._ensure_page()
                    
                    if intent == "BROWSER_OPEN":
                        url_val = dispatch.parameters.get("url") or dispatch.parameters.get("query") or ""
                        await page.goto(url_val)
                        return TaskResult(
                            task_id=dispatch.task_id,
                            agent_id=self.agent_id,
                            status=TaskStatus.SUCCESS,
                            payload={"success": True, "url": url_val},
                            correlation_id=dispatch.correlation_id
                        )
                    elif intent == "BROWSER_SEARCH":
                        query_val = dispatch.parameters.get("query") or ""
                        await page.goto(f"https://google.com/search?q={query_val}")
                        return TaskResult(
                            task_id=dispatch.task_id,
                            agent_id=self.agent_id,
                            status=TaskStatus.SUCCESS,
                            payload={"success": True, "query": query_val},
                            correlation_id=dispatch.correlation_id
                        )
                    elif intent == "BROWSER_FILL":
                        selector = dispatch.parameters.get("selector") or ""
                        text_val = dispatch.parameters.get("text") or dispatch.parameters.get("value") or ""
                        await page.locator(selector).fill(text_val)
                        return TaskResult(
                            task_id=dispatch.task_id,
                            agent_id=self.agent_id,
                            status=TaskStatus.SUCCESS,
                            payload={"success": True},
                            correlation_id=dispatch.correlation_id
                        )
                    elif intent == "BROWSER_CLICK":
                        selector = dispatch.parameters.get("selector") or ""
                        await page.locator(selector).click()
                        return TaskResult(
                            task_id=dispatch.task_id,
                            agent_id=self.agent_id,
                            status=TaskStatus.SUCCESS,
                            payload={"success": True},
                            correlation_id=dispatch.correlation_id
                        )
                    elif intent == "BROWSER_SCREENSHOT":
                        import uuid
                        os.makedirs("data/screenshots", exist_ok=True)
                        screenshot_path = f"data/screenshots/{uuid.uuid4()}.png"
                        await page.screenshot(path=screenshot_path)
                        return TaskResult(
                            task_id=dispatch.task_id,
                            agent_id=self.agent_id,
                            status=TaskStatus.SUCCESS,
                            payload={"success": True, "path": screenshot_path},
                            correlation_id=dispatch.correlation_id
                        )
                    elif intent == "BROWSER_CLOSE":
                        if self.browser:
                            await self.browser.close()
                            self.browser = None
                            self.playwright = None
                        return TaskResult(
                            task_id=dispatch.task_id,
                            agent_id=self.agent_id,
                            status=TaskStatus.SUCCESS,
                            payload={"success": True},
                            correlation_id=dispatch.correlation_id
                        )
                    elif intent == "WEB_SCRAPE":
                        url_val = dispatch.parameters.get("url") or ""
                        if not url_val:
                            raise ValueError("Scrape intent requires a 'url' parameter.")
                        await page.goto(url_val, timeout=10000)
                        title = await page.title()
                        content = await page.evaluate("() => document.body.innerText")
                        summary = content[:2000]
                        return TaskResult(
                            task_id=dispatch.task_id,
                            agent_id=self.agent_id,
                            status=TaskStatus.SUCCESS,
                            payload={"url": url_val, "title": title, "content": summary},
                            correlation_id=dispatch.correlation_id
                        )
                except Exception as e:
                    logger.warning(f"[WebAgent] Playwright browser operation failed: {e}")
                    return TaskResult(
                        task_id=dispatch.task_id,
                        agent_id=self.agent_id,
                        status=TaskStatus.PARTIAL,
                        payload={"error": str(e), "fallback": True},
                        correlation_id=dispatch.correlation_id
                    )
            else:
                # Path A (API Search) or default
                logger.info(f"[WebAgent] Executing API search path (Path A) for intent={intent}")
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
