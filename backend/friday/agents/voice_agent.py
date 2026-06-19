import asyncio
from uuid import uuid4
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus, EventEnvelope, EventPriority
from friday.core.event_bus import event_bus
from friday.agents.base_agent import BaseAgent
from voice.listen import listen as stt_listen, is_mic_enabled, reset_stop
from voice.speak import speak as tts_speak, cancel_play

class VoiceAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.VOICE_AGENT)
        self._stt_task = None

    async def startup(self) -> None:
        reset_stop()
        # Start the background STT stream loop
        self._stt_task = asyncio.create_task(self._stt_loop())
        logger.info("[VoiceAgent] STT listener loop started.")
        event_bus.subscribe("friday.agent.voice.tts_request", self.on_tts_request)
        logger.info("[VoiceAgent] Subscribed to friday.agent.voice.tts_request.")

    async def shutdown(self) -> None:
        if self._stt_task:
            self._stt_task.cancel()
            try:
                await self._stt_task
            except asyncio.CancelledError:
                pass
        cancel_play()
        event_bus.unsubscribe("friday.agent.voice.tts_request", self.on_tts_request)
        logger.info("[VoiceAgent] STT listener stopped and speech playback cancelled.")

    async def on_tts_request(self, envelope: EventEnvelope) -> None:
        payload = envelope.payload
        text = payload.get("text", "")
        corr_id = envelope.correlation_id
        session_id = envelope.session_id
        
        logger.info(f"[VoiceAgent] Received tts_request for correlation_id={corr_id}: '{text[:50]}'")
        
        try:
            # We call tts_speak (web_mode=False for local playback)
            web_mode = payload.get("web_mode", False)
            await tts_speak(text, web_mode=web_mode, response_id=str(corr_id))
            logger.info(f"[VoiceAgent] Speech playback finished for correlation_id={corr_id}")
        except Exception as e:
            logger.error(f"[VoiceAgent] Error during speak(): {e}")
        finally:
            # Publish friday.agent.voice.tts_complete
            complete_envelope = EventEnvelope(
                topic="friday.agent.voice.tts_complete",
                priority=EventPriority.P1,
                source="agent.voice.tts",
                correlation_id=corr_id,
                session_id=session_id,
                payload={"status": "complete"}
            )
            await event_bus.publish(complete_envelope)

    def get_capabilities(self) -> list[str]:
        return ["STT", "TTS", "INTERRUPT_DETECTION"]

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        if intent == "SPEAK":
            text = dispatch.parameters.get("text", "")
            web_mode = dispatch.parameters.get("web_mode", True)
            
            try:
                # Call existing robust speak module
                # Pass task_id as the response_id to correlate with completion events
                await tts_speak(text, web_mode=web_mode, response_id=str(dispatch.task_id))
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.SUCCESS,
                    payload={"response": "Speech completed successfully"},
                    correlation_id=dispatch.correlation_id
                )
            except Exception as e:
                logger.error(f"[VoiceAgent] Error in speak tool: {e}")
                return TaskResult(
                    task_id=dispatch.task_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.FAILED,
                    payload={"error": str(e)},
                    correlation_id=dispatch.correlation_id
                )
        else:
            return TaskResult(
                task_id=dispatch.task_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED,
                payload={"error": f"Unsupported intent: {intent}"},
                correlation_id=dispatch.correlation_id
            )

    async def _stt_loop(self):
        """Always-on microphone loop publishing transcriptions to perception layer."""
        while self._running:
            try:
                if not is_mic_enabled():
                    await asyncio.sleep(0.5)
                    continue

                # stt_listen() yields transcriptions using the thread-isolated recognizer
                query = await stt_listen()
                if query:
                    # Clean query and verify it is not noise
                    query_clean = query.strip()
                    if query_clean:
                        logger.info(f"[VoiceAgent] Transcribed speech: '{query_clean}'")
                        
                        # Generate new correlation ID for this request
                        correlation_id = uuid4()
                        
                        # Check for instant interrupt word
                        # In the new FSM core, the voice agent publishes P0 wake/interrupt events
                        # to immediately trigger FSM transition to INTERRUPTED state.
                        control_keywords = ("stop", "cancel", "interrupt", "never mind", "be quiet")
                        priority = EventPriority.P1
                        if any(kw in query_clean.lower() for kw in control_keywords):
                            logger.info(f"[VoiceAgent] Wake/Interrupt keyword detected. Setting priority to P0.")
                            priority = EventPriority.P0

                        envelope = EventEnvelope(
                            topic="friday.perception.voice.raw",
                            priority=priority,
                            source="agent.voice.stt",
                            correlation_id=correlation_id,
                            session_id=self.agent_id,  # Map to agent_id as placeholder session
                            payload={"text": query_clean, "is_voice": True}
                        )
                        await event_bus.publish(envelope)
                else:
                    from friday.core.fsm import cognitive_core, AssistantState
                    try:
                        if cognitive_core.fsm.current_state == AssistantState.LISTENING:
                            logger.info("[VoiceAgent] listen() returned None in LISTENING state. Resetting to IDLE.")
                            cognitive_core.fsm.transition_to(AssistantState.IDLE, reason="Speech ended with no content")
                    except Exception as e_state:
                        logger.error(f"[VoiceAgent] Error resetting state: {e_state}")
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[VoiceAgent] STT listener encountered error: {e}")
                await asyncio.sleep(1.0)
