"""
main.py — New Cognitive OS entry point.

Shutdown contract:
- This coroutine is run as a background asyncio.Task by api/server.py.
- When server shuts down it calls agent_task.cancel().
- We catch CancelledError, stop all agents, schedulers, cognitive core and event bus.
"""
import asyncio
import sys
from loguru import logger

from friday.core.event_bus import event_bus
from friday.core.agent_registry import agent_registry
from friday.core.schedulers.maintenance_scheduler import maintenance_scheduler
from friday.core.fsm import cognitive_core
from friday.agents import VoiceAgent, PCAgent, WebAgent, MemoryAgent, KnowledgeAgent
from friday.system.context import system_context
from voice.listen import reset_stop, request_stop, set_mic_enabled

async def main():
    reset_stop()
    set_mic_enabled(True)

    # Check Ollama availability once at startup
    try:
        import httpx
        from friday.core import fsm as fsm_module
        async with httpx.AsyncClient() as client:
            r = await client.get("http://localhost:11434/api/tags", timeout=1.0)
            if r.status_code == 200:
                fsm_module.OLLAMA_AVAILABLE = True
                logger.info("[COGNITIVE_OS] Ollama service detected and available.")
            else:
                fsm_module.OLLAMA_AVAILABLE = False
                logger.info("[COGNITIVE_OS] Ollama service returned non-200. Fallback offline.")
    except Exception as e_ollama:
        from friday.core import fsm as fsm_module
        fsm_module.OLLAMA_AVAILABLE = False
        logger.info(f"[COGNITIVE_OS] Ollama service not detected (will fallback to safe error string if Groq fails): {e_ollama}")

    logger.info("[COGNITIVE_OS] Preloading neural models and initializing components...")
    
    # 1. Start event bus
    # Event bus is started here if not already started by server lifespan
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    
    # 2. Start agent registry
    agent_registry.start()
    
    # 3. Spawn all 5 agents
    voice_agent = VoiceAgent()
    pc_agent = PCAgent()
    web_agent = WebAgent()
    memory_agent = MemoryAgent()
    knowledge_agent = KnowledgeAgent()
    
    # Start all 5 agents
    await voice_agent.start()
    await pc_agent.start()
    await web_agent.start()
    await memory_agent.start()
    await knowledge_agent.start()
    
    # Start system context
    await system_context.start(event_bus)
    
    # 4. Start maintenance scheduler
    maintenance_scheduler.start()
    
    # 5. Hand control to FSM (start CognitiveCore)
    cognitive_core.start(loop)
    
    logger.info("[COGNITIVE_OS] FRIDAY cognitive OS is fully booted and operational.")
    
    try:
        # Keep running indefinitely as an orchestrator task
        while True:
            await asyncio.sleep(3600)
            
    except asyncio.CancelledError:
        logger.info("[COGNITIVE_OS] Shutdown requested. Cleaning up subsystems...")
        
        # Publish shutdown event
        try:
            from friday.core.events import EventEnvelope, EventPriority
            from uuid import uuid4
            envelope = EventEnvelope(
                topic="friday.system.shutdown",
                priority=EventPriority.P0,
                source="cognitive_os",
                correlation_id=uuid4(),
                session_id=uuid4(),
                payload={}
            )
            await event_bus.publish(envelope)
            await asyncio.sleep(0.1)  # Let the event bus dispatch loop run to deliver the event
        except Exception as e_shut:
            logger.error(f"[COGNITIVE_OS] Failed to publish shutdown event: {e_shut}")
        
        # Stop FSM CognitiveCore
        cognitive_core.stop()
        
        # Stop system context
        system_context.stop()
        
        # Stop maintenance scheduler
        maintenance_scheduler.stop()
        
        # Stop all 5 agents
        await voice_agent.stop()
        await pc_agent.stop()
        await web_agent.stop()
        await memory_agent.stop()
        await knowledge_agent.stop()
        
        # Stop event bus
        await event_bus.stop()
        
        # Stop mic immediately
        request_stop()
        
        logger.info("[COGNITIVE_OS] Subsystems stopped cleanly.")
        raise
        
    except Exception as e:
        logger.error(f"[COGNITIVE_OS FATAL ERROR] {e}")
    finally:
        logger.info("[COGNITIVE_OS] FRIDAY offline")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[EXIT] Goodbye sir")
        sys.exit(0)
