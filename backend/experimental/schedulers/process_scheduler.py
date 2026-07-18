import asyncio
from typing import Callable, Any, Dict
from loguru import logger
from friday.core.events import AgentType

class ProcessScheduler:
    def __init__(self):
        # Store semaphores keyed by the active event loop to support multiple loops (like in tests)
        self._loop_semaphores: Dict[asyncio.AbstractEventLoop, Dict[str, Any]] = {}

    def _get_loop_context(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        if loop not in self._loop_semaphores:
            self._loop_semaphores[loop] = {
                "llm": asyncio.Semaphore(1),
                "tools": {
                    AgentType.WEB_AGENT: asyncio.Semaphore(3),
                    AgentType.PC_AGENT: asyncio.Semaphore(3),
                    AgentType.MEMORY_AGENT: asyncio.Semaphore(3),
                    AgentType.KNOWLEDGE_AGENT: asyncio.Semaphore(3),
                    AgentType.VOICE_AGENT: asyncio.Semaphore(3)
                }
            }
        return self._loop_semaphores[loop]

    async def schedule_llm(self, func: Callable, *args, **kwargs) -> Any:
        ctx = self._get_loop_context()
        sem = ctx["llm"]
        logger.debug("[ProcessScheduler] Queueing LLM inference request...")
        async with sem:
            logger.debug("[ProcessScheduler] Executing LLM inference.")
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return await asyncio.get_running_loop().run_in_executor(None, func, *args, **kwargs)

    async def schedule_tool(self, agent_type: AgentType, func: Callable, *args, **kwargs) -> Any:
        ctx = self._get_loop_context()
        semaphores = ctx["tools"]
        sem = semaphores.get(agent_type)
        if sem is None:
            sem = asyncio.Semaphore(3)
            semaphores[agent_type] = sem
            
        logger.debug(f"[ProcessScheduler] Requesting tool semaphore for {agent_type.value}...")
        async with sem:
            logger.debug(f"[ProcessScheduler] Executing tool for {agent_type.value}.")
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return await asyncio.get_running_loop().run_in_executor(None, func, *args, **kwargs)

    async def schedule_tts(self, func: Callable, *args, **kwargs) -> Any:
        logger.debug("[ProcessScheduler] Executing TTS play.")
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return await asyncio.get_running_loop().run_in_executor(None, func, *args, **kwargs)

process_scheduler = ProcessScheduler()
