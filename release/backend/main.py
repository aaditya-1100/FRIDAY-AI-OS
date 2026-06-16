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
from friday.agents import VoiceAgent, PCAgent, WebAgent, MemoryAgent, KnowledgeAgent, VisionAgent
from friday.system.context import system_context
from voice.listen import reset_stop, request_stop, set_mic_enabled
from friday.core.proactive_engine import proactive_engine

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
    
    # 3. Spawn all 6 agents
    voice_agent = VoiceAgent()
    pc_agent = PCAgent()
    web_agent = WebAgent()
    memory_agent = MemoryAgent()
    knowledge_agent = KnowledgeAgent()
    vision_agent = VisionAgent()
    
    # Start all 6 agents
    await voice_agent.start()
    await pc_agent.start()
    await web_agent.start()
    await memory_agent.start()
    await knowledge_agent.start()
    await vision_agent.start()
    
    # Start system context
    await system_context.start(event_bus)
    
    # 4. Start maintenance scheduler
    maintenance_scheduler.start()

    # Pre-warm spaCy model during startup
    logger.info("[COGNITIVE_OS] Pre-warming spaCy 'en_core_web_sm' model...")
    from brain.spacy_loader import get_spacy_model
    get_spacy_model()
    
    # Pre-warm ONNX intent parser model
    from brain.intent_parser import parse_intent
    try:
        parse_intent("hello")  # warms ONNX model before first real request
        logger.info("[COGNITIVE_OS] Intent parser ONNX model pre-warmed.")
    except Exception as e:
        logger.warning(f"[COGNITIVE_OS] Intent parser pre-warm failed (non-fatal): {e}")
    
    # 5. Hand control to FSM (start CognitiveCore)
    cognitive_core.start(loop)
    
    # Start proactive intelligence engine
    proactive_engine.start()
    
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
        
        # Stop proactive intelligence engine
        proactive_engine.stop()

        # Stop FSM CognitiveCore
        cognitive_core.stop()
        
        # Stop system context
        system_context.stop()
        
        # Stop maintenance scheduler
        maintenance_scheduler.stop()
        
        # Stop all 6 agents
        await voice_agent.stop()
        await pc_agent.stop()
        await web_agent.stop()
        await memory_agent.stop()
        await knowledge_agent.stop()
        await vision_agent.stop()
        
        # Stop event bus
        await event_bus.stop()
        
        # Stop mic immediately
        request_stop()
        
        logger.info("[COGNITIVE_OS] Subsystems stopped cleanly.")
        raise
        
    except Exception as e:
        logger.error(f"[COGNITIVE_OS FATAL ERROR] {e}")
    finally:
        try:
            from friday.memory.user_profile import user_profile
            await user_profile.flush()
        except Exception as e_prof:
            logger.error(f"[COGNITIVE_OS] Failed to flush user profile stats: {e_prof}")
        logger.info("[COGNITIVE_OS] FRIDAY offline")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[EXIT] Goodbye sir")
        sys.exit(0)
