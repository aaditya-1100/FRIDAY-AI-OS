import pytest
import asyncio
from uuid import uuid4
from pydantic import ValidationError

# Ensure backend folder is in sys.path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from loguru import logger
from friday.core.events import EventEnvelope, EventPriority
from friday.core.event_bus import EventBus
from friday.core.fsm import CognitiveFSM, AssistantState, FSMTransitionError
from friday.core.goal_stack import push_goal, update_goal_status, GoalStatus

@pytest.mark.asyncio
async def test_event_envelope_validation():
    # Verify missing correlation_id raises ValidationError
    with pytest.raises(ValidationError):
        EventEnvelope(
            topic="friday.perception.voice.raw",
            priority=EventPriority.P2,
            source="test",
            session_id=uuid4()
            # missing correlation_id
        )

    # Verify invalid topic format raises ValidationError
    with pytest.raises(ValidationError):
        EventEnvelope(
            topic="invalid_topic",
            priority=EventPriority.P2,
            source="test",
            correlation_id=uuid4(),
            session_id=uuid4()
        )

@pytest.mark.asyncio
async def test_event_bus_priority_dispatch():
    bus = EventBus()
    loop = asyncio.get_running_loop()
    bus.start(loop)

    received_events = []
    async def callback(envelope: EventEnvelope):
        received_events.append(envelope)

    bus.subscribe("friday.core.*", callback)

    # Pause dispatch loop by stopping it temporarily
    await bus.stop()
    
    c_id = uuid4()
    s_id = uuid4()
    e_p2 = EventEnvelope(
        topic="friday.core.state_change",
        priority=EventPriority.P2,
        source="test_p2",
        correlation_id=c_id,
        session_id=s_id
    )
    e_p0 = EventEnvelope(
        topic="friday.core.state_change",
        priority=EventPriority.P0,
        source="test_p0",
        correlation_id=c_id,
        session_id=s_id
    )

    await bus.publish(e_p2)
    await bus.publish(e_p0)

    # Start the loop again. It should process P0 first.
    bus.start(loop)
    
    await asyncio.sleep(0.2)
    await bus.stop()

    assert len(received_events) == 2
    assert received_events[0].priority == EventPriority.P0
    assert received_events[0].source == "test_p0"
    assert received_events[1].priority == EventPriority.P2
    assert received_events[1].source == "test_p2"

@pytest.mark.asyncio
async def test_topic_matching():
    bus = EventBus()
    loop = asyncio.get_running_loop()
    bus.start(loop)

    sub1_received = []
    async def cb1(env):
        sub1_received.append(env)

    bus.subscribe("friday.perception.*", cb1)

    c_id = uuid4()
    s_id = uuid4()
    env1 = EventEnvelope(
        topic="friday.perception.voice.raw",
        priority=EventPriority.P2,
        source="mic",
        correlation_id=c_id,
        session_id=s_id
    )
    await bus.publish(env1)

    await asyncio.sleep(0.2)
    await bus.stop()

    assert len(sub1_received) == 1
    assert sub1_received[0].topic == "friday.perception.voice.raw"

@pytest.mark.asyncio
async def test_fsm_transitions():
    fsm = CognitiveFSM()
    
    # IDLE -> PERCEIVING is valid
    fsm.transition_to(AssistantState.PERCEIVING)
    assert fsm.current_state == AssistantState.PERCEIVING

    # Attempting IDLE -> PLANNING directly raises FSMTransitionError
    fsm_idle = CognitiveFSM()
    with pytest.raises(FSMTransitionError):
        fsm_idle.transition_to(AssistantState.PLANNING)

    # Walk through a full successful cycle:
    # IDLE -> PERCEIVING -> PLANNING -> DELEGATING -> WAITING -> DELEGATING -> SYNTHESIZING -> RESPONDING -> REFLECTING -> IDLE
    fsm_cycle = CognitiveFSM()
    fsm_cycle.transition_to(AssistantState.PERCEIVING)
    fsm_cycle.transition_to(AssistantState.PLANNING)
    fsm_cycle.transition_to(AssistantState.DELEGATING)
    fsm_cycle.transition_to(AssistantState.WAITING)
    fsm_cycle.transition_to(AssistantState.DELEGATING)
    fsm_cycle.transition_to(AssistantState.SYNTHESIZING)
    fsm_cycle.transition_to(AssistantState.RESPONDING)
    fsm_cycle.transition_to(AssistantState.REFLECTING)
    fsm_cycle.transition_to(AssistantState.IDLE)
    assert fsm_cycle.current_state == AssistantState.IDLE

    # Verify that REFLECTING must return to IDLE
    fsm_reflect = CognitiveFSM()
    fsm_reflect.transition_to(AssistantState.PERCEIVING)
    fsm_reflect.transition_to(AssistantState.PLANNING)
    fsm_reflect.transition_to(AssistantState.SYNTHESIZING)
    fsm_reflect.transition_to(AssistantState.RESPONDING)
    fsm_reflect.transition_to(AssistantState.REFLECTING)
    with pytest.raises(FSMTransitionError):
        fsm_reflect.transition_to(AssistantState.PLANNING)  # cannot skip IDLE

@pytest.mark.asyncio
async def test_fsm_interrupted_and_error():
    fsm = CognitiveFSM()
    
    # Transition to PLANNING
    fsm.transition_to(AssistantState.PERCEIVING)
    fsm.transition_to(AssistantState.PLANNING)
    
    # P0 wakes up and triggers interrupt
    fsm.transition_to(AssistantState.INTERRUPTED)
    assert fsm.current_state == AssistantState.INTERRUPTED
    
    # Can go to IDLE
    fsm.transition_to(AssistantState.IDLE)
    assert fsm.current_state == AssistantState.IDLE

    # Verify error is terminal
    fsm.transition_to(AssistantState.ERROR)
    with pytest.raises(FSMTransitionError):
        fsm.transition_to(AssistantState.IDLE)

@pytest.mark.asyncio
async def test_fsm_goal_stack():
    goal_stack = []
    goal = push_goal(goal_stack, "Find cafes near me")
    assert len(goal_stack) == 1
    assert goal_stack[0]["description"] == "Find cafes near me"
    assert goal_stack[0]["status"] == GoalStatus.PENDING.value

    update_goal_status(goal_stack, goal.goal_id, GoalStatus.ACTIVE)
    assert goal_stack[0]["status"] == GoalStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_agent_mesh_and_registry():
    from unittest.mock import patch
    from friday.core.event_bus import event_bus
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    
    with patch("voice.listen.is_mic_enabled", return_value=False), \
         patch("voice.listen.listen", return_value=""), \
         patch("friday.agents.voice_agent.is_mic_enabled", return_value=False), \
         patch("friday.agents.voice_agent.stt_listen", return_value=""):
         
        from friday.core.agent_registry import agent_registry
        from friday.agents import VoiceAgent, PCAgent, WebAgent, MemoryAgent, KnowledgeAgent
        
        agent_registry.start()
        
        try:
            logger.info("Instantiating VoiceAgent...")
            voice = VoiceAgent()
            logger.info("Instantiating PCAgent...")
            pc = PCAgent()
            logger.info("Instantiating WebAgent...")
            web = WebAgent()
            logger.info("Instantiating MemoryAgent...")
            mem = MemoryAgent()
            logger.info("Instantiating KnowledgeAgent...")
            know = KnowledgeAgent()
            
            logger.info("Starting voice agent...")
            await voice.start()
            logger.info("Starting pc agent...")
            await pc.start()
            logger.info("Starting web agent...")
            await web.start()
            logger.info("Starting memory agent...")
            await mem.start()
            logger.info("Starting knowledge agent...")
            await know.start()
            
            logger.info("Waiting 0.5s...")
            await asyncio.sleep(0.5)
            
            assert len(agent_registry.agents) == 5
            assert str(voice.agent_id) in agent_registry.agents
            assert str(pc.agent_id) in agent_registry.agents
            assert str(web.agent_id) in agent_registry.agents
            assert str(mem.agent_id) in agent_registry.agents
            assert str(know.agent_id) in agent_registry.agents
            
            failed_agents = agent_registry.verify_heartbeats()
            assert len(failed_agents) == 0
            
            logger.info("Stopping voice agent...")
            await voice.stop()
            logger.info("Stopping pc agent...")
            await pc.stop()
            logger.info("Stopping web agent...")
            await web.stop()
            logger.info("Stopping memory agent...")
            await mem.stop()
            logger.info("Stopping knowledge agent...")
            await know.stop()
            logger.info("All agents stopped.")
        finally:
            await event_bus.stop()





@pytest.mark.asyncio
async def test_memory_pipeline_and_stores():
    from friday.memory.pipeline import memory_pipeline
    from friday.memory.episodic import EpisodicMemory
    from friday.memory.semantic import SemanticMemory
    
    episodic = EpisodicMemory()
    semantic = SemanticMemory()
    
    episodic.clear()
    semantic.clear()
    
    res_low = memory_pipeline.process_memory_formation(
        query="what is the weather?",
        intent="WEATHER",
        success=True,
        novelty=0.01,
        goal_relevance=0.01,
        emotional_weight=0.0,
        recency=0.1
    )
    assert res_low["status"] == "discarded"
    assert len(episodic.get_recent_episodes()) == 0
    
    res_high = memory_pipeline.process_memory_formation(
        query="Kashipur is my city.",
        intent="INFORM_FACT",
        success=True,
        novelty=0.8,
        goal_relevance=0.8,
        emotional_weight=0.5,
        recency=1.0
    )
    assert res_high["status"] == "stored"
    
    episodes = episodic.get_recent_episodes()
    assert len(episodes) == 1
    assert episodes[0]["query"] == "Kashipur is my city."
    
    hits = semantic.search("Kashipur")
    assert len(hits) > 0
    assert "Kashipur" in hits[0]["payload"]["text"]


@pytest.mark.asyncio
async def test_permission_and_audit_log():
    from friday.security.audit_log import audit_logger, AuditLogger
    from friday.security.permission_engine import permission_engine
    from friday.core.events import AgentType
    from friday.core.event_bus import event_bus
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    
    try:
        with pytest.raises(PermissionError):
            audit_logger._execute_query("DELETE FROM audit_log")
            
        with pytest.raises(PermissionError):
            audit_logger._execute_query("UPDATE audit_log SET granted=1")

        agent_id = uuid4()
        corr_id = uuid4()
        sess_id = uuid4()
        
        auth_task = asyncio.create_task(
            permission_engine.authorize_and_check(
                agent_id=agent_id,
                agent_type=AgentType.PC_AGENT,
                tool_name="SYSTEM_SHUTDOWN",
                correlation_id=corr_id,
                session_id=sess_id
            )
        )
        
        await asyncio.sleep(0.1)
        
        confirm_env = EventEnvelope(
            topic="friday.tool.user_confirmed",
            priority=EventPriority.P0,
            source="user_interface",
            correlation_id=corr_id,
            session_id=sess_id,
            payload={"confirmed": True}
        )
        await event_bus.publish(confirm_env)
        
        granted = await auth_task
        assert granted is True
        
        from friday.security.capability_registry import AGENT_TRUST_MAP
        from friday.core.events import AgentTrustLevel
        original_trust = AGENT_TRUST_MAP[AgentType.PC_AGENT]
        AGENT_TRUST_MAP[AgentType.PC_AGENT] = AgentTrustLevel.SANDBOXED
        try:
            denied_corr = uuid4()
            granted_priv = await permission_engine.authorize_and_check(
                agent_id=agent_id,
                agent_type=AgentType.PC_AGENT,
                tool_name="FILE_DELETE",
                correlation_id=denied_corr,
                session_id=sess_id
            )
            assert granted_priv is False
        finally:
            AGENT_TRUST_MAP[AgentType.PC_AGENT] = original_trust
        
        records = audit_logger.get_records()
        assert len(records) >= 2
        denial_record = next(r for r in records if r["correlation_id"] == str(denied_corr))
        assert denial_record["granted"] is False
        assert "insufficient" in denial_record["reason"]
    finally:
        await event_bus.stop()



@pytest.mark.asyncio
async def test_end_to_end_request_trace():
    from friday.core.event_bus import event_bus
    from friday.core.fsm import CognitiveFSM, CognitiveCore, AssistantState
    from friday.core.events import EventEnvelope, EventPriority, TaskResult, TaskStatus
    from uuid import uuid4
    import asyncio
    from unittest.mock import patch

    # 1. Initialize CognitiveCore and FSM
    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    core.start(loop)

    state_changes = []
    task_dispatches = []
    memory_writes = []
    responses = []

    async def on_state_change(env):
        state_changes.append(env)
        
    async def on_dispatch(env):
        task_dispatches.append(env)
        dispatch_payload = env.payload
        t_result = TaskResult(
            task_id=dispatch_payload["task_id"],
            agent_id=uuid4(),
            status=TaskStatus.SUCCESS,
            payload={"result": "The current time is 2:00 PM"},
            correlation_id=env.correlation_id
        )
        result_envelope = EventEnvelope(
            topic="friday.agent.pc_agent.result",
            priority=EventPriority.P2,
            source="mock.agent.pc",
            correlation_id=env.correlation_id,
            session_id=env.session_id,
            payload=t_result.model_dump()
        )
        await event_bus.publish(result_envelope)

    async def on_memory_write(env):
        memory_writes.append(env)

    async def on_response(env):
        responses.append(env)

    # Listen to TTS request and mock complete immediately
    async def on_tts_request(env):
        complete_envelope = EventEnvelope(
            topic="friday.agent.voice.tts_complete",
            priority=EventPriority.P1,
            source="agent.voice.tts",
            correlation_id=env.correlation_id,
            session_id=env.session_id,
            payload={"status": "complete"}
        )
        await event_bus.publish(complete_envelope)

    event_bus.subscribe("friday.core.state_change", on_state_change)
    event_bus.subscribe("friday.agent.pc_agent.dispatch", on_dispatch)
    event_bus.subscribe("friday.memory.write", on_memory_write)
    event_bus.subscribe("friday.core.response", on_response)
    event_bus.subscribe("friday.agent.voice.tts_request", on_tts_request)

    # Ensure FSM is in IDLE
    assert fsm.current_state == AssistantState.IDLE

    # 2. Publish a perception event
    c_id = uuid4()
    s_id = uuid4()
    perception_envelope = EventEnvelope(
        topic="friday.perception.text.input",
        priority=EventPriority.P1,
        source="user_interface",
        correlation_id=c_id,
        session_id=s_id,
        payload={"text": "what time is it"}
    )
    
    with patch("friday.core.fsm.parse_intent", return_value={"intent": "SYSTEM_STATUS", "confidence": 1.0}), \
         patch("friday.core.fsm.ask_groq", return_value="The current time is 2:00 PM"):
        await event_bus.publish(perception_envelope)

        # Wait for the turn to complete
        for _ in range(150):
            await asyncio.sleep(0.05)
            if fsm.current_state == AssistantState.IDLE and len(memory_writes) > 0:
                break

    # Clean up
    await asyncio.sleep(0.1)
    event_bus.unsubscribe("friday.core.state_change", on_state_change)
    event_bus.unsubscribe("friday.agent.pc_agent.dispatch", on_dispatch)
    event_bus.unsubscribe("friday.memory.write", on_memory_write)
    event_bus.unsubscribe("friday.core.response", on_response)
    event_bus.unsubscribe("friday.agent.voice.tts_request", on_tts_request)
    core.stop()
    await event_bus.stop()

    # Assertions
    assert fsm.current_state == AssistantState.IDLE
    assert len(state_changes) >= 8
    for env in state_changes:
        assert env.correlation_id == c_id

    assert len(task_dispatches) == 1
    assert task_dispatches[0].correlation_id == c_id

    assert len(responses) == 1
    assert responses[0].correlation_id == c_id

    assert len(memory_writes) == 1
    assert memory_writes[0].correlation_id == c_id

    states_traversed = [env.payload["new_state"] for env in state_changes]
    
    expected_order = [
        "PERCEIVING",
        "PLANNING",
        "DELEGATING",
        "WAITING",
        "SYNTHESIZING",
        "RESPONDING",
        "REFLECTING",
        "IDLE"
    ]
    assert states_traversed == expected_order
    assert len(memory_writes) == 1
    assert memory_writes[0].topic == "friday.memory.write"


@pytest.mark.asyncio
async def test_routing_table():
    from friday.core.routing_table import INTENT_TO_AGENT, DIRECT_LLM_INTENTS, MULTI_ACTION_INTENT
    assert INTENT_TO_AGENT["WEB_SEARCH"] == "WEB_AGENT"
    assert INTENT_TO_AGENT["CASUAL_CHAT"] is None
    assert INTENT_TO_AGENT["AI_QUERY"] is None
    assert INTENT_TO_AGENT["MULTI_ACTION"] == "MULTI"
    for intent in DIRECT_LLM_INTENTS:
        assert INTENT_TO_AGENT[intent] is None


@pytest.mark.asyncio
async def test_intent_to_fsm_wiring():
    from unittest.mock import patch, MagicMock
    from friday.core.event_bus import event_bus
    from friday.core.fsm import CognitiveFSM, CognitiveCore, AssistantState
    from friday.core.events import EventEnvelope, EventPriority
    from uuid import uuid4
    
    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    core.start(loop)
    
    async def on_tts_request(env):
        complete_envelope = EventEnvelope(
            topic="friday.agent.voice.tts_complete",
            priority=EventPriority.P1,
            source="agent.voice.tts",
            correlation_id=env.correlation_id,
            session_id=env.session_id,
            payload={"status": "complete"}
        )
        await event_bus.publish(complete_envelope)

    event_bus.subscribe("friday.agent.voice.tts_request", on_tts_request)
    
    try:
        # Mock parse_intent to return low confidence (0.4)
        mocked_parse = MagicMock(return_value={"intent": "OPEN", "confidence": 0.4})
        
        with patch("friday.core.fsm.parse_intent", mocked_parse), \
             patch("friday.core.fsm.ask_groq", return_value="What would you like me to open, sir?"):
             
            # Track states
            state_changes = []
            async def on_state_change(env):
                state_changes.append(env.payload["new_state"])
            event_bus.subscribe("friday.core.state_change", on_state_change)
            
            c_id = uuid4()
            s_id = uuid4()
            env1 = EventEnvelope(
                topic="friday.perception.text.input",
                priority=EventPriority.P1,
                source="test",
                correlation_id=c_id,
                session_id=s_id,
                payload={"text": "open"}
            )
            await event_bus.publish(env1)
            
            # Wait for FSM to return to IDLE
            for _ in range(150):
                await asyncio.sleep(0.05)
                if fsm.current_state == AssistantState.IDLE:
                    break
            
            event_bus.unsubscribe("friday.core.state_change", on_state_change)
            
            # Verify states: should NOT go to DELEGATING or WAITING
            # Flow: PERCEIVING -> PLANNING -> SYNTHESIZING -> RESPONDING -> REFLECTING -> IDLE
            assert "PERCEIVING" in state_changes
            assert "PLANNING" in state_changes
            assert "SYNTHESIZING" in state_changes
            assert "DELEGATING" not in state_changes
            assert "WAITING" not in state_changes
            assert "REFLECTING" in state_changes
            assert fsm.current_state == AssistantState.IDLE
    finally:
        event_bus.unsubscribe("friday.agent.voice.tts_request", on_tts_request)
        core.stop()
        await event_bus.stop()


@pytest.mark.asyncio
async def test_llm_synthesizing():
    from unittest.mock import patch, AsyncMock, MagicMock
    from friday.core.fsm import CognitiveFSM, CognitiveCore, AssistantState
    from friday.core.events import EventEnvelope, EventPriority
    from friday.core.event_bus import event_bus
    from uuid import uuid4
    
    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    core.start(loop)
    
    async def on_tts_request(env):
        complete_envelope = EventEnvelope(
            topic="friday.agent.voice.tts_complete",
            priority=EventPriority.P1,
            source="agent.voice.tts",
            correlation_id=env.correlation_id,
            session_id=env.session_id,
            payload={"status": "complete"}
        )
        await event_bus.publish(complete_envelope)

    event_bus.subscribe("friday.agent.voice.tts_request", on_tts_request)
    
    try:
        # Mock groq client response
        with patch("friday.core.fsm.ask_groq", return_value="Groq Synthesized Answer") as mock_ask_groq:
            c_id = uuid4()
            s_id = uuid4()
            
            with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}):
                env1 = EventEnvelope(
                    topic="friday.perception.text.input",
                    priority=EventPriority.P1,
                    source="test",
                    correlation_id=c_id,
                    session_id=s_id,
                    payload={"text": "hello"}
                )
                await event_bus.publish(env1)
                
                for _ in range(150):
                    await asyncio.sleep(0.05)
                    if fsm.current_state == AssistantState.IDLE:
                        break
            
            assert mock_ask_groq.called
            assert fsm.working_memory.get("response") == "Groq Synthesized Answer" or fsm.current_state == AssistantState.IDLE
                
        # Now test fallback chain
        with patch("friday.core.fsm.ask_groq", side_effect=TimeoutError("Groq timeout")), \
             patch("friday.core.fsm.OLLAMA_AVAILABLE", True), \
             patch("httpx.AsyncClient.post") as mock_post:
             
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"message": {"content": "Ollama Synthesized Answer"}}
            mock_post.return_value = mock_resp
            
            fsm2 = CognitiveFSM()
            core2 = CognitiveCore(fsm=fsm2)
            core2.start(loop)
            
            try:
                with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}):
                    c_id2 = uuid4()
                    env2 = EventEnvelope(
                        topic="friday.perception.text.input",
                        priority=EventPriority.P1,
                        source="test",
                        correlation_id=c_id2,
                        session_id=uuid4(),
                        payload={"text": "hello"}
                    )
                    await event_bus.publish(env2)
                    
                    for _ in range(150):
                        await asyncio.sleep(0.05)
                        if fsm2.current_state == AssistantState.IDLE:
                            break
                
                assert mock_post.called
            finally:
                core2.stop()
    finally:
        event_bus.unsubscribe("friday.agent.voice.tts_request", on_tts_request)
        core.stop()
        await event_bus.stop()


@pytest.mark.asyncio
async def test_tts_responding():
    from unittest.mock import patch, MagicMock
    from friday.core.fsm import CognitiveFSM, CognitiveCore, AssistantState
    from friday.core.events import EventEnvelope, EventPriority
    from friday.core.event_bus import event_bus
    from uuid import uuid4
    
    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    core.start(loop)
    
    try:
        # Mock speak
        with patch("voice.speak.speak", return_value=None):
            tts_requests = []
            async def on_tts_request(env):
                tts_requests.append(env)
                complete_envelope = EventEnvelope(
                    topic="friday.agent.voice.tts_complete",
                    priority=EventPriority.P1,
                    source="agent.voice.tts",
                    correlation_id=env.correlation_id,
                    session_id=env.session_id,
                    payload={"status": "complete"}
                )
                await event_bus.publish(complete_envelope)
                
            event_bus.subscribe("friday.agent.voice.tts_request", on_tts_request)
            
            with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}), \
                 patch("friday.core.fsm.ask_groq", return_value="TTS test response"):
                 
                c_id = uuid4()
                env1 = EventEnvelope(
                    topic="friday.perception.text.input",
                    priority=EventPriority.P1,
                    source="test",
                    correlation_id=c_id,
                    session_id=uuid4(),
                    payload={"text": "hello"}
                )
                await event_bus.publish(env1)
                
                for _ in range(150):
                    await asyncio.sleep(0.05)
                    if fsm.current_state == AssistantState.IDLE:
                        break
                        
            event_bus.unsubscribe("friday.agent.voice.tts_request", on_tts_request)
            assert len(tts_requests) == 1
            assert tts_requests[0].payload["text"] == "TTS test response"
            
        # Test timeout path
        original_wait_for = asyncio.wait_for
        
        async def mock_wait_for_timeout(fut, timeout, **kwargs):
            if timeout == 200.0:
                raise asyncio.TimeoutError()
            return await original_wait_for(fut, timeout, **kwargs)
            
        with patch("asyncio.wait_for", side_effect=mock_wait_for_timeout):
            fsm3 = CognitiveFSM()
            core3 = CognitiveCore(fsm=fsm3)
            core3.start(loop)
            
            try:
                with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}), \
                     patch("friday.core.fsm.ask_groq", return_value="TTS timeout response"):
                     
                    c_id3 = uuid4()
                    env3 = EventEnvelope(
                        topic="friday.perception.text.input",
                        priority=EventPriority.P1,
                        source="test",
                        correlation_id=c_id3,
                        session_id=uuid4(),
                        payload={"text": "hello"}
                    )
                    await event_bus.publish(env3)
                    
                    for _ in range(150):
                        await asyncio.sleep(0.05)
                        if fsm3.current_state == AssistantState.IDLE:
                            break
                            
                assert fsm3.current_state == AssistantState.IDLE
            finally:
                core3.stop()
    finally:
        core.stop()
        await event_bus.stop()


@pytest.mark.asyncio
async def test_memory_reflection():
    from unittest.mock import patch
    from friday.core.fsm import CognitiveFSM, CognitiveCore, AssistantState
    from friday.core.events import EventEnvelope, EventPriority
    from friday.core.event_bus import event_bus
    from friday.memory.episodic import EpisodicMemory
    from friday.agents.memory_agent import MemoryAgent
    from uuid import uuid4
    
    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    core.start(loop)
    
    mem_agent = MemoryAgent()
    await mem_agent.start()
    
    async def on_tts_request(env):
        complete_envelope = EventEnvelope(
            topic="friday.agent.voice.tts_complete",
            priority=EventPriority.P1,
            source="agent.voice.tts",
            correlation_id=env.correlation_id,
            session_id=env.session_id,
            payload={"status": "complete"}
        )
        await event_bus.publish(complete_envelope)

    event_bus.subscribe("friday.agent.voice.tts_request", on_tts_request)
    
    try:
        episodic = EpisodicMemory()
        episodic.clear()
        
        with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}), \
             patch("friday.core.fsm.ask_groq", return_value="Memory test response"):
             
            c_id = uuid4()
            write_event = asyncio.Event()
            async def on_write_complete(e):
                if e.correlation_id == c_id:
                    write_event.set()
            event_bus.subscribe("friday.memory.write_complete", on_write_complete)
            
            try:
                env = EventEnvelope(
                    topic="friday.perception.text.input",
                    priority=EventPriority.P1,
                    source="test",
                    correlation_id=c_id,
                    session_id=uuid4(),
                    payload={"text": "remember my favorite color is blue"}
                )
                await event_bus.publish(env)
                
                await asyncio.wait_for(write_event.wait(), timeout=15.0)
                
                for _ in range(150):
                    if fsm.current_state == AssistantState.IDLE:
                        break
                    await asyncio.sleep(0.05)
            finally:
                event_bus.unsubscribe("friday.memory.write_complete", on_write_complete)
            
            episodes = episodic.get_recent_episodes()
            assert len(episodes) >= 1
            assert "favorite color is blue" in episodes[0]["query"]
    finally:
        event_bus.unsubscribe("friday.agent.voice.tts_request", on_tts_request)
        await mem_agent.stop()
        core.stop()
        await event_bus.stop()


@pytest.mark.asyncio
async def test_memory_retrieval_in_planning():
    from friday.core.fsm import CognitiveFSM, CognitiveCore, AssistantState
    from friday.core.event_bus import event_bus
    from friday.memory.semantic import SemanticMemory
    from friday.memory.episodic import EpisodicMemory
    from friday.memory.session import SessionMemory
    from friday.core.events import EventEnvelope, EventPriority
    from unittest.mock import patch, MagicMock
    from uuid import uuid4
    import asyncio
    
    sem = SemanticMemory()
    sem.clear()
    sem.add_fact("Aaditya's favorite framework is FastAPI", metadata={"intent": "INFORM_FACT"})
    
    epi = EpisodicMemory()
    epi.clear()
    epi.add_episode("what is Aaditya's favorite framework?", "AI_QUERY", True, 0.9, {"response": "FastAPI"})
    
    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    core.start(loop)
    
    async def on_tts_request(env):
        complete_envelope = EventEnvelope(
            topic="friday.agent.voice.tts_complete",
            priority=EventPriority.P1,
            source="agent.voice.tts",
            correlation_id=env.correlation_id,
            session_id=env.session_id,
            payload={"status": "complete"}
        )
        await event_bus.publish(complete_envelope)

    event_bus.subscribe("friday.agent.voice.tts_request", on_tts_request)
    
    try:
        c_id = uuid4()
        s_id = uuid4()
        
        with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}), \
             patch("friday.core.fsm.ask_groq", return_value="FastAPI") as mock_groq:
             
            perception_env = EventEnvelope(
                topic="friday.perception.text.input",
                priority=EventPriority.P1,
                source="test",
                correlation_id=c_id,
                session_id=s_id,
                payload={"text": "favorite framework"}
            )
            await event_bus.publish(perception_env)
            
            for _ in range(150):
                await asyncio.sleep(0.05)
                if fsm.current_state == AssistantState.IDLE:
                    break
            await asyncio.sleep(0.1)
            
            assert mock_groq.called
            called_args, called_kwargs = mock_groq.call_args
            sys_prompt = called_kwargs.get("system_prompt", "")
            assert "Relevant context from memory" in sys_prompt
            assert "Recent conversation history" in sys_prompt
            
        import time
        def mock_search_slow(*args, **kwargs):
            time.sleep(0.6)
            return [{"payload": {"text": "ignored"}}]
            
        core.stop()
        fsm2 = CognitiveFSM()
        core2 = CognitiveCore(fsm=fsm2)
        core2.start(loop)
        
        c_id2 = uuid4()
        with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}), \
             patch("friday.core.fsm.ask_groq", return_value="FastAPI") as mock_groq2, \
             patch("friday.core.fsm.SemanticMemory.search", side_effect=mock_search_slow):
             
            perception_env2 = EventEnvelope(
                topic="friday.perception.text.input",
                priority=EventPriority.P1,
                source="test",
                correlation_id=c_id2,
                session_id=uuid4(),
                payload={"text": "favorite framework"}
            )
            await event_bus.publish(perception_env2)
            
            for _ in range(150):
                await asyncio.sleep(0.05)
                if fsm2.current_state == AssistantState.IDLE:
                    break
            await asyncio.sleep(0.1)
                    
            assert mock_groq2.called
            called_args2, called_kwargs2 = mock_groq2.call_args
            sys_prompt2 = called_kwargs2.get("system_prompt", "")
            assert "ignored" not in sys_prompt2
            assert fsm2.current_state == AssistantState.IDLE
            
        core2.stop()
    finally:
        event_bus.unsubscribe("friday.agent.voice.tts_request", on_tts_request)
        core.stop()
        await event_bus.stop()


@pytest.mark.asyncio
async def test_conversation_history():
    from friday.core.fsm import CognitiveFSM, CognitiveCore, AssistantState
    from friday.core.event_bus import event_bus
    from friday.memory.session import SessionMemory
    from friday.core.events import EventEnvelope, EventPriority
    from unittest.mock import patch, MagicMock
    from uuid import uuid4
    import asyncio
    import json
    
    session = SessionMemory()
    await session.clear()
    
    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    core.start(loop)
    
    async def on_tts_request(env):
        complete_envelope = EventEnvelope(
            topic="friday.agent.voice.tts_complete",
            priority=EventPriority.P1,
            source="agent.voice.tts",
            correlation_id=env.correlation_id,
            session_id=env.session_id,
            payload={"status": "complete"}
        )
        await event_bus.publish(complete_envelope)

    event_bus.subscribe("friday.agent.voice.tts_request", on_tts_request)
    
    try:
        responses = ["response 1", "response 2", "response 3"]
        queries = ["query 1", "query 2", "query 3"]
        groq_calls = []
        
        for i in range(3):
            def mock_ask(query_val, system_prompt=None, model=None, history=None, timeout=None):
                groq_calls.append(history.copy() if history else [])
                return responses[i]
                
            c_id = uuid4()
            with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}), \
                 patch("friday.core.fsm.ask_groq", side_effect=mock_ask):
                 
                perception_env = EventEnvelope(
                    topic="friday.perception.text.input",
                    priority=EventPriority.P1,
                    source="test",
                    correlation_id=c_id,
                    session_id=fsm.session_id,
                    payload={"text": queries[i]}
                )
                await event_bus.publish(perception_env)
                
                for _ in range(150):
                    await asyncio.sleep(0.05)
                    if fsm.current_state == AssistantState.IDLE:
                        break
                await asyncio.sleep(0.1)
                
        history = await session.get("conversation_history")
        assert len(history) == 6
        assert history[0]["content"] == "query 1"
        assert history[1]["content"] == "response 1"
        assert history[4]["content"] == "query 3"
        assert history[5]["content"] == "response 3"
        
        assert len(groq_calls) == 3
        assert len(groq_calls[0]) == 0
        assert len(groq_calls[1]) == 2
        assert len(groq_calls[2]) == 4
        assert groq_calls[2][0]["content"] == "query 1"
        assert groq_calls[2][1]["content"] == "response 1"
        assert groq_calls[2][2]["content"] == "query 2"
        assert groq_calls[2][3]["content"] == "response 2"
        
        large_history = []
        for j in range(50):
            large_history.append({"role": "user", "content": "a" * 150})
            large_history.append({"role": "assistant", "content": "b" * 150})
            
        assert len(json.dumps(large_history)) > 6000
        await session.set("conversation_history", large_history)
        
        c_id_trunc = uuid4()
        with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}), \
             patch("friday.core.fsm.ask_groq", return_value="trunc response"):
             
            perception_env_trunc = EventEnvelope(
                topic="friday.perception.text.input",
                priority=EventPriority.P1,
                source="test",
                correlation_id=c_id_trunc,
                session_id=fsm.session_id,
                payload={"text": "trunc query"}
            )
            await event_bus.publish(perception_env_trunc)
            
            for _ in range(150):
                await asyncio.sleep(0.05)
                if fsm.current_state == AssistantState.IDLE:
                    break
            await asyncio.sleep(0.1)
            
        final_history = await session.get("conversation_history")
        assert len(json.dumps(final_history)) / 3 <= 2000
        assert final_history[-2]["content"] == "trunc query"
        assert final_history[-1]["content"] == "trunc response"
        
    finally:
        event_bus.unsubscribe("friday.agent.voice.tts_request", on_tts_request)
        core.stop()
        await event_bus.stop()


@pytest.mark.asyncio
async def test_web_agent_api_only():
    from friday.agents.web_agent import WebAgent
    from friday.core.events import TaskDispatch, AgentType
    from unittest.mock import patch, MagicMock
    from uuid import uuid4
    
    web = WebAgent()
    await web.start()
    
    mock_ddgs_results = [
        {"title": "Result 1", "href": "http://res1.com", "body": "Snippet 1"},
        {"title": "Result 2", "href": "http://res2.com", "body": "Snippet 2"},
        {"title": "Result 3", "href": "http://res3.com", "body": "Snippet 3"},
    ]
    
    class MockDDGS:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def text(self, q, max_results=5):
            return mock_ddgs_results
            
    try:
        dispatch_web = TaskDispatch(
            task_id=uuid4(),
            session_id=uuid4(),
            agent_type=AgentType.WEB_AGENT,
            intent="WEB_SEARCH",
            parameters={"query": "test query"},
            correlation_id=uuid4()
        )
        
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}), \
             patch("friday.agents.web_agent.DDGS", return_value=MockDDGS()) as mock_ddg_class, \
             patch.object(web, "_ensure_browser", create=True) as mock_ensure_browser:
             
            res = await web.handle_task(dispatch_web)
            mock_ensure_browser.assert_not_called()
            assert res.status.value == "SUCCESS"
            results = res.payload.get("results", [])
            assert len(results) == 3
            assert results[0]["title"] == "Result 1"
            assert results[0]["url"] == "http://res1.com"
            assert results[0]["snippet"] == "Snippet 1"
            
        dispatch_search = TaskDispatch(
            task_id=uuid4(),
            session_id=uuid4(),
            agent_type=AgentType.WEB_AGENT,
            intent="SEARCH",
            parameters={"query": "test query"},
            correlation_id=uuid4()
        )
        
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}), \
             patch("friday.agents.web_agent.DDGS", return_value=MockDDGS()) as mock_ddg_class, \
             patch.object(web, "_ensure_browser", create=True) as mock_ensure_browser:
             
            res = await web.handle_task(dispatch_search)
            mock_ensure_browser.assert_not_called()
            assert res.status.value == "SUCCESS"
            assert len(res.payload.get("results", [])) == 3
            
    finally:
        await web.stop()



@pytest.mark.asyncio
async def test_redis_session():
    from friday.memory.session import SessionMemory
    
    session = SessionMemory()
    await session.set("test_key", "test_val")
    val = await session.get("test_key")
    assert val == "test_val"
    
    await session.delete("test_key")
    assert await session.get("test_key") is None


@pytest.mark.asyncio
async def test_pc_action_permissions():
    from friday.agents.pc_agent import PCAgent
    from friday.core.events import AgentTrustLevel, TaskDispatch, TaskStatus, AgentType
    from friday.security.audit_log import audit_logger
    from friday.core.event_bus import event_bus
    from uuid import uuid4
    import sqlite3
    
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    
    try:
        conn = sqlite3.connect(audit_logger.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_log")
        conn.commit()
        conn.close()
        
        agent = PCAgent()
        agent.trust_level = AgentTrustLevel.STANDARD
        
        # R8.1: SYSTEM_STATUS is handled natively by PCAgent — no monolith patch needed
        dispatch_status = TaskDispatch(
            task_id=uuid4(),
            session_id=uuid4(),
            agent_type=AgentType.PC_AGENT,
            intent="SYSTEM_STATUS",
            parameters={},
            correlation_id=uuid4()
        )
        res_status = await agent.handle_task(dispatch_status)
        assert res_status.status == TaskStatus.SUCCESS
            
        agent_sandbox = PCAgent()
        agent_sandbox.trust_level = AgentTrustLevel.SANDBOXED
        dispatch_delete = TaskDispatch(
            task_id=uuid4(),
            session_id=uuid4(),
            agent_type=AgentType.PC_AGENT,
            intent="FILE_DELETE",
            parameters={"path": "C:/FRIDAY/test.txt"},
            correlation_id=uuid4()
        )
        res_delete = await agent_sandbox.handle_task(dispatch_delete)
        assert res_delete.status == TaskStatus.FAILED
        assert "Permission denied" in res_delete.payload["error"]
        
        confirm_called = asyncio.Event()
        async def on_confirm_req(env):
            confirm_called.set()
            from friday.core.events import EventEnvelope, EventPriority
            confirm_reply = EventEnvelope(
                topic="friday.tool.user_confirmed",
                priority=EventPriority.P0,
                source="test_UI",
                correlation_id=env.correlation_id,
                session_id=env.session_id,
                payload={}
            )
            await event_bus.publish(confirm_reply)
            
        event_bus.subscribe("friday.tool.confirm_required", on_confirm_req)
        
        try:
            dispatch_shutdown = TaskDispatch(
                task_id=uuid4(),
                session_id=uuid4(),
                agent_type=AgentType.PC_AGENT,
                intent="SEND_EMAIL",
                parameters={},
                correlation_id=uuid4()
            )
            # R8.1: SEND_EMAIL is not a PCAgent intent — correctly returns FAILED (unhandled).
            res_shutdown = await agent.handle_task(dispatch_shutdown)
            assert res_shutdown.status == TaskStatus.FAILED
        finally:
            event_bus.unsubscribe("friday.tool.confirm_required", on_confirm_req)
            
        conn = sqlite3.connect(audit_logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tool_name, granted FROM audit_log")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) >= 2  # At least SYSTEM_STATUS + FILE_DELETE logged
        statuses = {r[0]: r[1] for r in rows}
        assert statuses.get("SYSTEM_STATUS") == 1
        assert statuses.get("FILE_DELETE") == 0
    finally:
        await event_bus.stop()


@pytest.mark.asyncio
async def test_browser_task_types():
    from friday.agents.web_agent import WebAgent
    from friday.core.events import AgentTrustLevel, TaskDispatch, TaskStatus, AgentType
    from unittest.mock import AsyncMock, patch
    from uuid import uuid4
    
    agent = WebAgent()
    agent.trust_level = AgentTrustLevel.STANDARD
    
    mock_page = AsyncMock()
    
    with patch.object(agent, "_ensure_browser", AsyncMock(), create=True), \
         patch.object(agent, "_ensure_page", AsyncMock(return_value=mock_page), create=True):
         
        dispatch_open = TaskDispatch(
            task_id=uuid4(),
            session_id=uuid4(),
            agent_type=AgentType.WEB_AGENT,
            intent="BROWSER_OPEN",
            parameters={"url": "https://example.com"},
            correlation_id=uuid4()
        )
        res_open = await agent.handle_task(dispatch_open)
        assert res_open.status == TaskStatus.FAILED
        # R8.1: error message updated to match new WebAgent format
        assert "WebAgent does not handle intent" in res_open.payload["error"]
        
        dispatch_shot = TaskDispatch(
            task_id=uuid4(),
            session_id=uuid4(),
            agent_type=AgentType.WEB_AGENT,
            intent="BROWSER_SCREENSHOT",
            parameters={},
            correlation_id=uuid4()
        )
        res_shot = await agent.handle_task(dispatch_shot)
        assert res_shot.status == TaskStatus.FAILED
        assert "WebAgent does not handle intent" in res_shot.payload["error"]
        
    agent_sandboxed = WebAgent()
    agent_sandboxed.trust_level = AgentTrustLevel.SANDBOXED
    dispatch_fill = TaskDispatch(
        task_id=uuid4(),
        session_id=uuid4(),
        agent_type=AgentType.WEB_AGENT,
        intent="BROWSER_FILL",
        parameters={"selector": "#input", "text": "hello"},
        correlation_id=uuid4()
    )
    res_fill = await agent_sandboxed.handle_task(dispatch_fill)
    assert res_fill.status == TaskStatus.FAILED
    # SANDBOXED agent is rejected by permission_engine before intent routing
    assert "Permission denied" in res_fill.payload["error"] or "WebAgent does not handle intent" in res_fill.payload["error"]


def test_mcp_schemas():
    from friday.tools.mcp_schemas import MCP_TOOL_REGISTRY
    
    assert len(MCP_TOOL_REGISTRY) >= 12
    
    required_names = {
        "web_search", "browser_open", "file_read", "file_write", "file_delete",
        "app_open", "app_close", "system_status", "set_reminder", "screenshot",
        "clipboard_read", "clipboard_write"
    }
    
    names_in_registry = set()
    for tool in MCP_TOOL_REGISTRY:
        for key in ["name", "description", "input_schema", "permission_level"]:
            assert key in tool
            
        assert isinstance(tool["input_schema"], dict)
        assert tool["input_schema"].get("type") == "object"
        
        perm_level = tool["permission_level"]
        assert perm_level in ["READ_ONLY", "WRITE_SAFE", "ELEVATED", "PRIVILEGED", "HUMAN_CONFIRMED"]
        names_in_registry.add(tool["name"])
        
    for name in required_names:
        assert name in names_in_registry


@pytest.mark.asyncio
async def test_system_context():
    from friday.system.context import SystemContext
    from friday.core.events import EventEnvelope
    from unittest.mock import AsyncMock, MagicMock, patch
    
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()
    
    ctx = SystemContext()
    ctx.collect_metrics()
    
    context_data = ctx.get_context()
    assert "current_time" in context_data
    assert context_data["current_time"] != ""
    assert "battery_level" in context_data
    assert "cpu_percent" in context_data
    
    with patch("pygetwindow.getActiveWindow", side_effect=Exception("Mock Window Error")):
        ctx.collect_metrics()
        assert ctx.active_window is None
        
    await ctx.start(mock_bus)
    await asyncio.sleep(0.05)
    try:
        mock_bus.publish.assert_called()
        args = mock_bus.publish.call_args[0][0]
        assert isinstance(args, EventEnvelope)
        assert args.topic == "friday.system.context_update"
    finally:
        ctx.stop()


def test_system_prompt_assembly():
    from friday.core.system_prompt import assemble_system_prompt
    
    mock_wm = {
        "agent_results": [
            {"task_id": "t1", "status": "SUCCESS", "payload": {"data": "ok"}}
        ],
        "memory_context": {
            "semantic_facts": ["fact A", "fact B"],
            "recent_episodes": [{"query": "hello", "response": "world"}]
        },
        "conversation_history": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"}
        ]
    }
    
    mock_context = {
        "current_time": "2026-06-10T12:00:00",
        "current_date": "2026-06-10",
        "battery_level": 85.0,
        "active_window": "VS Code",
        "cpu_percent": 15.0,
        "memory_percent": 60.0
    }
    
    prompt = assemble_system_prompt(mock_wm, mock_context)
    
    for header in ["1. Identity", "2. Behavioral Rules", "3. System Context", "4. Tool Results", "5. Memory Context", "6. Conversation History"]:
        assert header in prompt
        
    mock_wm_empty_mem = mock_wm.copy()
    mock_wm_empty_mem["memory_context"] = {}
    prompt_empty_mem = assemble_system_prompt(mock_wm_empty_mem, mock_context)
    assert "5. Memory Context" not in prompt_empty_mem
    
    huge_wm = {
        "agent_results": [
            {"task_id": f"t{i}", "status": "SUCCESS", "payload": "x" * 2000} for i in range(10)
        ],
        "memory_context": {
            "semantic_facts": ["fact " * 3000],
            "recent_episodes": [{"query": "hello", "response": "world"}]
        },
        "conversation_history": [
            {"role": "user", "content": "hello" * 1000} for _ in range(10)
        ]
    }
    
    huge_prompt = assemble_system_prompt(huge_wm, mock_context)
    assert "1. Identity" in huge_prompt
    assert "2. Behavioral Rules" in huge_prompt
    assert len(huge_prompt) / 3 <= 8500


@pytest.mark.asyncio
async def test_screen_reader():
    from friday.vision.screen_reader import screen_reader, TESSERACT_AVAILABLE
    from PIL import Image
    import time
    from unittest.mock import patch

    # Mock screenshot
    img = Image.new("RGB", (100, 100), color="white")
    with patch.object(screen_reader, "screenshot", return_value=img):
        captured = screen_reader.screenshot()
        assert isinstance(captured, Image.Image)
        assert captured.size == (100, 100)
        
    if TESSERACT_AVAILABLE:
        txt = screen_reader.extract_text(img)
        assert isinstance(txt, str)
    else:
        txt = screen_reader.extract_text(img)
        assert txt == ""
        
    bbox = screen_reader.find_text(img, "nonexistent")
    assert bbox is None
    
    # Test timeout
    def slow_screenshot():
        time.sleep(4.0)
        return img
        
    with patch.object(screen_reader, "screenshot", side_effect=slow_screenshot):
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.to_thread(screen_reader.screenshot), timeout=1.0)


@pytest.mark.asyncio
async def test_vision_agent():
    from friday.agents.vision_agent import VisionAgent
    from friday.core.events import TaskDispatch, TaskResult, TaskStatus, AgentType
    from friday.vision.screen_reader import screen_reader
    from PIL import Image
    from uuid import uuid4
    from unittest.mock import patch

    agent = VisionAgent()
    await agent.start()
    
    img = Image.new("RGB", (50, 50), color="blue")
    mock_structured = {"full_text": "mock text", "text_blocks": [], "active_window": "TestWindow"}
    
    with patch.object(screen_reader, "screenshot", return_value=img), \
         patch.object(screen_reader, "extract_structured", return_value=mock_structured), \
         patch.object(screen_reader, "extract_text", return_value="mock raw text"):
         
        # Dispatch SCREEN_READ
        dispatch_read = TaskDispatch(
            task_id=uuid4(),
            agent_id=agent.agent_id,
            agent_type=AgentType.VISION_AGENT,
            intent="SCREEN_READ",
            parameters={},
            correlation_id=uuid4(),
            session_id=uuid4()
        )
        res_read = await agent.handle_task(dispatch_read)
        assert res_read.status == TaskStatus.SUCCESS
        assert res_read.payload["full_text"] == "mock text"
        assert "text_blocks" in res_read.payload
        
        # Dispatch SCREEN_SCREENSHOT
        dispatch_shot = TaskDispatch(
            task_id=uuid4(),
            agent_id=agent.agent_id,
            agent_type=AgentType.VISION_AGENT,
            intent="SCREEN_SCREENSHOT",
            parameters={},
            correlation_id=uuid4(),
            session_id=uuid4()
        )
        res_shot = await agent.handle_task(dispatch_shot)
        assert res_shot.status == TaskStatus.SUCCESS
        assert "path" in res_shot.payload
        assert os.path.exists(res_shot.payload["path"])
        if os.path.exists(res_shot.payload["path"]):
            os.remove(res_shot.payload["path"])
            
        # Dispatch SCREEN_DESCRIBE
        dispatch_desc = TaskDispatch(
            task_id=uuid4(),
            agent_id=agent.agent_id,
            agent_type=AgentType.VISION_AGENT,
            intent="SCREEN_DESCRIBE",
            parameters={},
            correlation_id=uuid4(),
            session_id=uuid4()
        )
        res_desc = await agent.handle_task(dispatch_desc)
        assert res_desc.status == TaskStatus.SUCCESS
        assert res_desc.payload["ocr_text"] == "Mock raw text"
        
    await agent.stop()


@pytest.mark.asyncio
async def test_proactive_engine():
    from friday.core.proactive_engine import ProactiveEngine
    from friday.core.fsm import cognitive_core, AssistantState
    from friday.core.events import EventEnvelope, EventPriority
    from friday.core.event_bus import event_bus
    from uuid import uuid4
    from unittest.mock import patch
    
    event_bus._subscribers.clear()
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    
    engine = ProactiveEngine()
    engine.start()
    
    triggers = []
    async def on_trigger(env):
        triggers.append(env)
    event_bus.subscribe("friday.core.proactive_trigger", on_trigger)
    class MockProcess:
        def __init__(self, name):
            self.info = {'name': name}
            
    with patch("psutil.process_iter", return_value=[MockProcess("code.exe")]):
        try:
            cognitive_core.current_state = AssistantState.IDLE
            
            # 1. LOW_BATTERY trigger
            context_env = EventEnvelope(
                topic="friday.system.context_update",
                priority=EventPriority.P3,
                source="test",
                correlation_id=uuid4(),
                session_id=uuid4(),
                payload={"battery_level": 0.15, "cpu_percent": 10.0, "memory_percent": 50.0}
            )
            await event_bus.publish(context_env)
            await asyncio.sleep(0.3)
            
            assert len(triggers) == 1
            assert triggers[0].payload["rule"] == "LOW_BATTERY"
            
            # 2. Cooldown check
            await event_bus.publish(context_env)
            await asyncio.sleep(0.3)
            assert len(triggers) == 1
            
            # 3. HIGH_CPU double-tick test
            cpu_env_1 = EventEnvelope(
                topic="friday.system.context_update",
                priority=EventPriority.P3,
                source="test",
                correlation_id=uuid4(),
                session_id=uuid4(),
                payload={"battery_level": 0.80, "cpu_percent": 90.0, "memory_percent": 50.0}
            )
            engine.rule_last_fired.pop("HIGH_CPU", None)
            await event_bus.publish(cpu_env_1)
            await asyncio.sleep(0.3)
            assert len(triggers) == 1
            
            cpu_env_2 = EventEnvelope(
                topic="friday.system.context_update",
                priority=EventPriority.P3,
                source="test",
                correlation_id=uuid4(),
                session_id=uuid4(),
                payload={"battery_level": 0.80, "cpu_percent": 95.0, "memory_percent": 50.0}
            )
            await event_bus.publish(cpu_env_2)
            await asyncio.sleep(0.3)
            assert len(triggers) == 2
            assert triggers[1].payload["rule"] == "HIGH_CPU"
            
            # 4. State check suppression
            cognitive_core.current_state = AssistantState.SYNTHESIZING
            engine.rule_last_fired.pop("LOW_BATTERY", None)
            await event_bus.publish(context_env)
            await asyncio.sleep(0.3)
            assert len(triggers) == 2
        finally:
            engine.stop()
        event_bus.unsubscribe("friday.core.proactive_trigger", on_trigger)
        await event_bus.stop()


def test_screen_aware_prompt():
    from friday.core.system_prompt import assemble_system_prompt
    
    mock_wm = {
        "agent_results": [],
        "memory_context": {},
        "conversation_history": []
    }
    mock_context = {
        "current_time": "2026-06-10T12:00:00",
        "current_date": "2026-06-10"
    }
    
    screen_ctx = {"ocr_text": "Hello screen OCR text", "active_window": "Notepad"}
    prompt = assemble_system_prompt(mock_wm, mock_context, screen_context=screen_ctx)
    assert "3b. Screen Context" in prompt
    assert "Current screen: Notepad" in prompt
    assert "Screen text (excerpt): Hello screen OCR text" in prompt
    
    prompt_no_screen = assemble_system_prompt(mock_wm, mock_context, screen_context=None)
    assert "3b. Screen Context" not in prompt_no_screen
    
    huge_ocr = "A" * 600
    screen_ctx_huge = {"ocr_text": huge_ocr, "active_window": "Notepad"}
    prompt_huge = assemble_system_prompt(mock_wm, mock_context, screen_context=screen_ctx_huge)
    assert "A" * 500 in prompt_huge
    assert "A" * 501 not in prompt_huge


@pytest.mark.asyncio
async def test_user_profile():
    import tempfile
    from friday.memory.user_profile import UserProfile
    from unittest.mock import patch
    
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    try:
        profile = UserProfile()
        profile.sqlite_path = temp_db_path
        profile.stats = {"hour": {}, "app": {}, "intent": {}, "entity": {}}
        profile._init_sqlite()
        
        import datetime
        hour = datetime.datetime.now().hour
        
        await profile.record_turn("OPEN", ["file"], "Notepad", hour)
        await profile.record_turn("SYSTEM_STATUS", [], "VS Code", hour)
        await profile.record_turn("FILE_READ", ["code"], "VS Code", hour)
        await profile.record_turn("FILE_WRITE", ["script"], "Word", hour)
        await profile.record_turn("WEB_SEARCH", [], "Chrome", hour)
        
        await profile.flush()
        profile.load()
        
        top_intents = profile.get_top_n("intent", 5)
        assert len(top_intents) >= 3
        
        hours = profile.get_active_hours()
        assert str(hour) in hours
        assert hours[str(hour)] == 5
        
        new_profile = UserProfile()
        new_profile.sqlite_path = temp_db_path
        new_profile.load()
        
        assert new_profile.get_active_hours().get(str(hour)) == 5
        assert len(new_profile.get_top_n("intent", 5)) >= 3
        
    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

@pytest.mark.asyncio
async def test_tts_long_playback_timeout_cutoff():
    from friday.core.fsm import CognitiveFSM, CognitiveCore, AssistantState
    from friday.core.events import EventEnvelope, EventPriority
    from friday.core.event_bus import event_bus
    from unittest.mock import patch
    from uuid import uuid4
    import asyncio

    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    core.start(loop)
    
    c_id = uuid4()
    envelope = EventEnvelope(
        topic="friday.perception.text.input",
        priority=EventPriority.P1,
        source="test",
        correlation_id=c_id,
        session_id=fsm.session_id,
        payload={"text": "hello"}
    )
    
    wait_for_calls = []
    async def mock_wait_for(fut, timeout=None):
        if timeout is not None:
            wait_for_calls.append(timeout)
        async def fire_complete():
            await asyncio.sleep(0.05)
            complete_envelope = EventEnvelope(
                topic="friday.agent.voice.tts_complete",
                priority=EventPriority.P1,
                source="agent.voice.tts",
                correlation_id=c_id,
                session_id=fsm.session_id,
                payload={"status": "complete"}
            )
            await event_bus.publish(complete_envelope)
        asyncio.create_task(fire_complete())
        return await fut

    with patch("friday.core.fsm.parse_intent", return_value={"intent": "CASUAL_CHAT", "confidence": 1.0}), \
         patch("friday.core.fsm.ask_groq", return_value="hello back"), \
         patch("friday.core.fsm.asyncio.wait_for", side_effect=mock_wait_for), \
         patch("friday.core.fsm.SessionMemory") as mock_session_class:
         
         mock_session = mock_session_class.return_value
         async def mock_get(*args, **kwargs): return []
         async def mock_set(*args, **kwargs): pass
         mock_session.get = mock_get
         mock_session.set = mock_set
         
         await event_bus.publish(envelope)
         
         for _ in range(50):
             await asyncio.sleep(0.02)
             if fsm.current_state == AssistantState.IDLE:
                 break
                 
         assert 200.0 in wait_for_calls
         assert fsm.current_state == AssistantState.IDLE


@pytest.mark.asyncio
async def test_high_memory_proactive_silent_trigger():
    from friday.core.fsm import CognitiveFSM, CognitiveCore, AssistantState
    from friday.core.events import EventEnvelope, EventPriority
    from friday.core.event_bus import event_bus
    from uuid import uuid4
    import asyncio

    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    loop = asyncio.get_running_loop()
    event_bus.start(loop)
    core.start(loop)
    
    assert fsm.current_state == AssistantState.IDLE
    
    c_id = uuid4()
    envelope = EventEnvelope(
        topic="friday.core.proactive_trigger",
        priority=EventPriority.P2,
        source="proactive_engine",
        correlation_id=c_id,
        session_id=uuid4(),
        payload={
            "rule": "HIGH_MEMORY",
            "message": "Memory usage is at 91.9%. Applications may slow down."
        }
    )
    
    await event_bus.publish(envelope)
    await asyncio.sleep(0.1)
    
    assert fsm.current_state == AssistantState.IDLE
    assert core.active_correlation_id is None or core.active_correlation_id != c_id
