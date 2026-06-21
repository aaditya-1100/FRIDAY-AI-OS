import asyncio
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.security.permission_engine import permission_engine
from execution.action_executor import execute_youtube_capability
from system.chrome_opener import open_url_in_chrome

class MediaAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.MEDIA_AGENT)

    async def startup(self) -> None:
        logger.info("[MediaAgent] Startup complete.")

    async def shutdown(self) -> None:
        logger.info("[MediaAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return [
            "YOUTUBE_TOPIC_SEARCH",
            "LATEST_CREATOR_VIDEO",
            "LATEST_CREATOR_SHORT",
            "VIDEO_BY_TITLE",
            "CHANNEL_OPEN",
            "PLAY_SEARCH_RESULT",
            "PLAY_MEDIA",
            "URL_OPEN"
        ]

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        parameters = dispatch.parameters or {}
        
        # Ensure we have the query parameter
        if "query" not in parameters and "url" in parameters:
            parameters["query"] = parameters["url"]
        elif "query" not in parameters:
            parameters["query"] = ""

        # 1. Permission Check
        allowed = await permission_engine.check_permission(
            agent_trust_level=self.trust_level,
            tool_name=intent,
            agent_id=self.agent_id,
            correlation_id=dispatch.correlation_id,
            session_id=dispatch.session_id
        )
        if not allowed:
            logger.warning(f"[MediaAgent] Permission denied for intent: {intent}")
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": "Permission denied"},
                correlation_id=dispatch.correlation_id
            )

        try:
            loop = asyncio.get_running_loop()
            if intent == "URL_OPEN":
                url = parameters.get("url") or parameters.get("query") or ""
                url = url.strip()
                logger.info(f"[MediaAgent] Opening URL in Chrome: {url}")
                success = open_url_in_chrome(url)
                status = TaskStatus.SUCCESS if success else TaskStatus.FAILED
                payload = {"success": success}
                if not success:
                    payload["error"] = "Failed to launch Chrome with requested URL."
                
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=status,
                    payload=payload,
                    correlation_id=dispatch.correlation_id
                )
            
            else:
                # YouTube capabilities
                logger.info(f"[MediaAgent] Executing YouTube capability '{intent}' with parameters: {parameters}")
                result = await execute_youtube_capability(intent, parameters, loop)
                status = TaskStatus.SUCCESS if result is not False else TaskStatus.FAILED
                payload = result if isinstance(result, dict) else {"success": bool(result)}
                
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=status,
                    payload=payload,
                    correlation_id=dispatch.correlation_id
                )

        except Exception as e:
            logger.error(f"[MediaAgent] Error handling task {intent}: {e}", exc_info=True)
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": str(e)},
                correlation_id=dispatch.correlation_id
            )
