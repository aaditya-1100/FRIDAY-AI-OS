import asyncio
import os
from uuid import uuid4
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.security.permission_engine import permission_engine
from friday.vision.screen_reader import screen_reader
from friday.system.context import system_context

class VisionAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.VISION_AGENT)

    async def startup(self) -> None:
        logger.info("[VisionAgent] Startup complete.")

    async def shutdown(self) -> None:
        logger.info("[VisionAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return ["SCREEN_READ", "SCREEN_FIND", "SCREEN_SCREENSHOT", "SCREEN_DESCRIBE"]

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        parameters = dispatch.parameters or {}

        # 1. Permission Check
        allowed = await permission_engine.check_permission(
            agent_trust_level=self.trust_level,
            tool_name=intent,
            agent_id=self.agent_id,
            correlation_id=dispatch.correlation_id,
            session_id=dispatch.session_id
        )
        if not allowed:
            logger.warning(f"[VisionAgent] Permission denied for intent: {intent}")
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": "Permission denied"},
                correlation_id=dispatch.correlation_id
            )

        try:
            if intent == "SCREEN_READ":
                image = await asyncio.to_thread(screen_reader.screenshot)
                result = await asyncio.to_thread(screen_reader.extract_structured, image)
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload=result,
                    correlation_id=dispatch.correlation_id
                )

            elif intent == "SCREEN_FIND":
                query = parameters.get("query") or ""
                image = await asyncio.to_thread(screen_reader.screenshot)
                bbox = await asyncio.to_thread(screen_reader.find_text, image, query)
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"found": bbox is not None, "bbox": bbox},
                    correlation_id=dispatch.correlation_id
                )

            elif intent == "SCREEN_SCREENSHOT":
                image = await asyncio.to_thread(screen_reader.screenshot)
                BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                SCREENSHOTS_DIR = os.path.join(BASE_DIR, "data", "screenshots")
                os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
                path = os.path.join(SCREENSHOTS_DIR, f"{uuid4()}.png")
                await asyncio.to_thread(image.save, path)
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"path": path},
                    correlation_id=dispatch.correlation_id
                )

            elif intent == "SCREEN_DESCRIBE":
                image = await asyncio.to_thread(screen_reader.screenshot)
                ocr_text = await asyncio.to_thread(screen_reader.extract_text, image)
                active_window = system_context.get_context().get("active_window", "")
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"ocr_text": ocr_text, "active_window": active_window},
                    correlation_id=dispatch.correlation_id
                )

            else:
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.FAILED,
                    payload={"error": f"Unknown vision intent: {intent}"},
                    correlation_id=dispatch.correlation_id
                )

        except Exception as e:
            logger.error(f"[VisionAgent] Failed to handle task {intent}: {e}")
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": str(e)},
                correlation_id=dispatch.correlation_id
            )
