import sys
from unittest.mock import MagicMock, patch
import pytest
import asyncio

# autouse fixture to patch sys.modules only during test execution of tests in this file
@pytest.fixture(autouse=True)
def mock_external_modules():
    modules_patch = {
        "qdrant_client": MagicMock(),
        "friday.memory.session": MagicMock(),
        "friday.memory.semantic": MagicMock(),
        "friday.memory.episodic": MagicMock(),
        "friday.memory.knowledge_graph": MagicMock(),
        "brain.spacy_loader": MagicMock(),
        "friday.agents.pc_agent": MagicMock()
    }
    with patch.dict(sys.modules, modules_patch):
        yield

from friday.core.fsm import AssistantState, CognitiveFSM, CognitiveCore
import friday.core.fsm as fsm_module
from core.runtime_stability import RuntimeStabilityManager

@pytest.mark.asyncio
async def test_watchdog_stuck_recovery():
    # 1. Initialize FSM and CognitiveCore
    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    
    # Wire the global cognitive_core singleton for the watchdog to read
    old_core = fsm_module.cognitive_core
    fsm_module.cognitive_core = core
    
    try:
        # 2. Put FSM into a stuck state (e.g. WAITING)
        fsm.transition_to(AssistantState.PERCEIVING, "start")
        fsm.transition_to(AssistantState.PLANNING, "plan")
        fsm.transition_to(AssistantState.DELEGATING, "delegate")
        fsm.transition_to(AssistantState.WAITING, "wait")
        
        assert fsm.current_state == AssistantState.WAITING
        
        # 3. Setup watchdog manager
        loop = asyncio.get_running_loop()
        janitor = RuntimeStabilityManager(loop=loop)
        
        # Manually inject state duration (stuck for 50 seconds)
        janitor._state_durations[AssistantState.WAITING] = 50.0
        
        # Mock health audit to avoid disk/network checks
        janitor.run_health_audit = MagicMock(return_value={})
        
        # Patch asyncio.sleep to run once and then exit the loop
        sleep_count = 0
        async def mock_sleep(delay):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count > 1:
                raise asyncio.CancelledError()
            
        with patch("asyncio.sleep", mock_sleep), \
             patch("voice.speak.cancel_play") as mock_cancel_play:
             
            # Start watchdog loop and let it process one tick
            try:
                await janitor._watchdog_loop()
            except asyncio.CancelledError:
                pass
            
            # Assert that FSM was reset to IDLE and current turn was aborted
            assert fsm.current_state == AssistantState.IDLE
            mock_cancel_play.assert_called_once()
            
    finally:
        # Restore global singleton
        fsm_module.cognitive_core = old_core
