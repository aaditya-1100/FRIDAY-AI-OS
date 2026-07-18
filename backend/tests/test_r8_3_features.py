import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from friday.core.events import TaskDispatch, TaskStatus
from friday.agents.pc_agent import PCAgent

@pytest.mark.asyncio
async def test_window_close_fuzzy_match():
    # Enumerate matches for a single window close
    class MockWindow:
        def __init__(self, title, hwnd):
            self.title = title
            self._hWnd = hwnd
            self.close = MagicMock()

    win1 = MockWindow("Google Chrome", 123)
    win2 = MockWindow("Visual Studio Code", 456)
    win3 = MockWindow("Notepad", 789)

    agent = PCAgent()
    
    # Mock gw.getAllWindows
    with patch("pygetwindow.getAllWindows", return_value=[win1, win2, win3]), \
         patch("pygetwindow.getActiveWindow", return_value=win1):
         
        # Case 1: Fuzzy match exact 1 window ("Chrome")
        dispatch = TaskDispatch(
            task_id="t1", agent_type="PC_AGENT", intent="WINDOW_CONTROL",
            parameters={"command": "close", "target": "Chrome"},
            correlation_id="c1", session_id="s1"
        )
        res = await agent.handle_task(dispatch)
        assert res.status == TaskStatus.SUCCESS
        assert "Google Chrome" in res.payload.get("response") or "Chrome" in res.payload.get("response") or "Closed the window" in res.payload.get("response")

        # Case 2: Fuzzy match exact 1 window ("code")
        dispatch = TaskDispatch(
            task_id="t2", agent_type="PC_AGENT", intent="WINDOW_CONTROL",
            parameters={"command": "close", "target": "code"},
            correlation_id="c2", session_id="s2"
        )
        res = await agent.handle_task(dispatch)
        assert res.status == TaskStatus.SUCCESS
        assert "Code" in res.payload.get("response") or "code" in res.payload.get("response") or "Closed the window" in res.payload.get("response")

        # Case 3: Fuzzy match multiple windows ("o") -> "Google Chrome", "Visual Studio Code", "Notepad" all contain 'o'
        dispatch = TaskDispatch(
            task_id="t3", agent_type="PC_AGENT", intent="WINDOW_CONTROL",
            parameters={"command": "close", "target": "o"},
            correlation_id="c3", session_id="s3"
        )
        res = await agent.handle_task(dispatch)
        assert res.status == TaskStatus.SUCCESS
        assert "multiple windows" in res.payload.get("response")

        # Case 4: Fuzzy match zero windows ("xyz")
        dispatch = TaskDispatch(
            task_id="t4", agent_type="PC_AGENT", intent="WINDOW_CONTROL",
            parameters={"command": "close", "target": "xyz"},
            correlation_id="c4", session_id="s4"
        )
        res = await agent.handle_task(dispatch)
        assert res.status == TaskStatus.SUCCESS
        assert "No open window matching" in res.payload.get("response")

@pytest.mark.asyncio
async def test_deletion_guard_live():
    agent = PCAgent()

    # Case 1: Tier 1 blocked path (e.g. C:\Windows)
    dispatch = TaskDispatch(
        task_id="td1", agent_type="PC_AGENT", intent="DELETE_PATH",
        parameters={"path": "C:/Windows"},
        correlation_id="c1", session_id="s1"
    )
    res = await agent.handle_task(dispatch)
    assert res.status == TaskStatus.FAILED
    assert "Cannot delete system path" in res.payload.get("error")

    # Case 2: Unblocked path deletion mock
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = f.name
    
    # Mock deletion guard's send2trash or delete_to_recycle_bin
    with patch("friday.security.deletion_guard.send2trash") as mock_trash:
        dispatch = TaskDispatch(
            task_id="td2", agent_type="PC_AGENT", intent="DELETE_PATH",
            parameters={"path": temp_path},
            correlation_id="c2", session_id="s2"
        )
        
        # Mock exists check to represent a deleted file
        with patch.object(Path, "exists", return_value=False):
            res = await agent.handle_task(dispatch)
            assert res.status == TaskStatus.SUCCESS
            assert "Deleted" in res.payload.get("response")

@pytest.mark.asyncio
async def test_terminal_whitelist_enforcement():
    agent = PCAgent()

    # Case 1: CHECK_DISK_SPACE
    with patch("friday.security.terminal_whitelist.check_disk_space", return_value="Drive C: 50GB free") as mock_check:
        dispatch = TaskDispatch(
            task_id="tw1", agent_type="PC_AGENT", intent="CHECK_DISK_SPACE",
            parameters={}, correlation_id="c1", session_id="s1"
        )
        res = await agent.handle_task(dispatch)
        assert res.status == TaskStatus.SUCCESS
        assert res.payload.get("output") == "Drive C: 50GB free"
        mock_check.assert_called_once()

    # Case 2: PING_HOST
    with patch("friday.security.terminal_whitelist.ping_host", return_value="Ping OK") as mock_ping:
        dispatch = TaskDispatch(
            task_id="tw2", agent_type="PC_AGENT", intent="PING_HOST",
            parameters={"host": "google.com"}, correlation_id="c2", session_id="s2"
        )
        res = await agent.handle_task(dispatch)
        assert res.status == TaskStatus.SUCCESS
        assert res.payload.get("output") == "Ping OK"
        mock_ping.assert_called_once_with("google.com")

@pytest.mark.asyncio
async def test_interruption_mid_speech():
    from friday.core.fsm import AssistantState
    
    with patch("voice.speak.cancel_play") as mock_cancel_play, \
         patch("friday.core.fsm.cognitive_core") as mock_core:
         
        from friday.core.control import cancel_speak
        cancel_speak()
        
        mock_cancel_play.assert_called_once()
        mock_core.fsm.transition_to.assert_called_once_with(AssistantState.IDLE, reason="Cancellation requested", force=True)

@pytest.mark.asyncio
async def test_multi_action_chain():
    from execution.action_executor import execute_action
    
    async def mock_dispatch(action, memory=None):
        intent = action.get("intent")
        if intent == "OPEN":
            return {"type": "ai_response", "response": f"Opened {action.get('target')}."}
        elif intent == "WEATHER":
            return {"type": "ai_response", "response": f"Weather in {action.get('location')} is sunny."}
        elif intent == "FAIL_INTENT":
            return False
        return None

    with patch("execution.action_executor._dispatch_to_agent", side_effect=mock_dispatch):
        # Case 1: 2 successful actions
        intent_data = {
            "intent": "MULTI_ACTION",
            "actions": [
                {"intent": "OPEN", "target": "Notepad"},
                {"intent": "WEATHER", "location": "Paris"}
            ]
        }
        res = await execute_action(intent_data)
        assert res == {"type": "ai_response", "response": "Opened Notepad. Weather in Paris is sunny."}

        # Case 2: One success, one failure
        intent_data_with_fail = {
            "intent": "MULTI_ACTION",
            "actions": [
                {"intent": "OPEN", "target": "Notepad"},
                {"intent": "FAIL_INTENT"}
            ]
        }
        res_fail = await execute_action(intent_data_with_fail)
        assert res_fail == {"type": "ai_response", "response": "Opened Notepad. Step 2 (FAIL_INTENT) failed."}

        # Case 3: More than 3 actions - check truncation to first 3
        intent_data_four = {
            "intent": "MULTI_ACTION",
            "actions": [
                {"intent": "OPEN", "target": "Notepad"},
                {"intent": "WEATHER", "location": "Paris"},
                {"intent": "OPEN", "target": "Paint"},
                {"intent": "OPEN", "target": "Word"}
            ]
        }
        res_four = await execute_action(intent_data_four)
        assert res_four == {"type": "ai_response", "response": "Opened Notepad. Weather in Paris is sunny. Opened Paint."}

@pytest.mark.asyncio
async def test_screen_click_intent():
    from friday.agents.vision_agent import VisionAgent
    agent = VisionAgent()
    
    # Case 1: Search bar heuristic path click
    with patch("pyautogui.size", return_value=(1920, 1080)), \
         patch("pyautogui.click") as mock_click:
         
        dispatch = TaskDispatch(
            task_id="tc1", agent_type="VISION_AGENT", intent="SCREEN_CLICK",
            parameters={"target": "search bar"}, correlation_id="c1", session_id="s1"
        )
        res = await agent.handle_task(dispatch)
        assert res.status == TaskStatus.SUCCESS
        assert "Clicked" in res.payload.get("response")
        mock_click.assert_called_once_with(960, 86)

    # Case 2: VLM mock response (found=True)
    class MockResponse:
        status_code = 200
        def json(self):
            return {"response": '{"x": 500, "y": 300, "found": true, "element": "submit button"}'}

    with patch("pyautogui.size", return_value=(1920, 1080)), \
         patch("pyautogui.click") as mock_click, \
         patch("httpx.post", return_value=MockResponse()):
         
        dispatch = TaskDispatch(
            task_id="tc2", agent_type="VISION_AGENT", intent="SCREEN_CLICK",
            parameters={"target": "submit button"}, correlation_id="c2", session_id="s2"
        )
        res = await agent.handle_task(dispatch)
        assert res.status == TaskStatus.SUCCESS
        assert "Clicked the submit button at (500, 300)" in res.payload.get("response")
        mock_click.assert_called_once_with(500, 300)

    # Case 3: VLM coordinate outside screen bounds (y is in taskbar or invalid)
    class MockOutBoundsResponse:
        status_code = 200
        def json(self):
            return {"response": '{"x": 500, "y": 1050, "found": true, "element": "taskbar"}'}

    with patch("pyautogui.size", return_value=(1920, 1080)), \
         patch("pyautogui.click") as mock_click, \
         patch("httpx.post", return_value=MockOutBoundsResponse()):
         
        dispatch = TaskDispatch(
            task_id="tc3", agent_type="VISION_AGENT", intent="SCREEN_CLICK",
            parameters={"target": "taskbar"}, correlation_id="c3", session_id="s3"
        )
        res = await agent.handle_task(dispatch)
        assert res.status == TaskStatus.FAILED
        assert "protected system area" in res.payload.get("error")
        mock_click.assert_not_called()

@pytest.mark.asyncio
async def test_spotify_auth_flow():
    import os
    from friday.agents.media_agent import MediaAgent
    
    agent = MediaAgent()
    
    mock_keyring_db = {}
    def mock_set_password(service, username, password):
        mock_keyring_db[f"{service}:{username}"] = password
    def mock_get_password(service, username):
        return mock_keyring_db.get(f"{service}:{username}")
        
    class MockTokenResponse:
        status_code = 200
        def json(self):
            return {
                "access_token": "mock_access",
                "refresh_token": "mock_refresh",
                "expires_in": 3600
            }
            
    class MockPlayerResponse:
        status_code = 204
        def json(self):
            return {}

    with patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "mock_client_id"}), \
         patch("keyring.set_password", side_effect=mock_set_password), \
         patch("keyring.get_password", side_effect=mock_get_password), \
         patch("webbrowser.open") as mock_web_open, \
         patch("friday.integrations.spotify_auth.run_loopback_server", return_value="auth_code_123"), \
         patch("httpx.AsyncClient.request", return_value=MockPlayerResponse()), \
         patch("httpx.AsyncClient.post", return_value=MockTokenResponse()):
         
        dispatch1 = TaskDispatch(
            task_id="ts1", agent_type="MEDIA_AGENT", intent="SPOTIFY_CONTROL",
            parameters={"command": "play"}, correlation_id="c1", session_id="s1"
        )
        res1 = await agent.handle_task(dispatch1)
        assert res1.status == TaskStatus.SUCCESS
        assert "Playing Spotify" in res1.payload.get("response")
        mock_web_open.assert_called_once()
        
        assert mock_get_password("FRIDAY", "spotify_tokens") is not None
        
        mock_web_open.reset_mock()
        dispatch2 = TaskDispatch(
            task_id="ts2", agent_type="MEDIA_AGENT", intent="SPOTIFY_CONTROL",
            parameters={"command": "pause"}, correlation_id="c2", session_id="s2"
        )
        res2 = await agent.handle_task(dispatch2)
        assert res2.status == TaskStatus.SUCCESS
        assert "Pausing Spotify" in res2.payload.get("response")
        mock_web_open.assert_not_called()

@pytest.mark.asyncio
async def test_context_mode_detection():
    from friday.core.proactive_engine import ProactiveEngine
    from friday.core.events import EventEnvelope, EventPriority
    from uuid import uuid4
    
    class MockProcess:
        def __init__(self, name):
            self.info = {'name': name}
            
    engine = ProactiveEngine()
    
    with patch("psutil.process_iter", return_value=[MockProcess("code.exe")]), \
         patch("friday.core.fsm.cognitive_core.current_state", "IDLE"):
         
        envelope = EventEnvelope(
            topic="friday.system.context_update",
            priority=EventPriority.P3,
            source="system.context",
            correlation_id=uuid4(),
            session_id=uuid4(),
            payload={"active_window": "some title", "cpu_percent": 10.0, "memory_percent": 50.0}
        )
        
        await engine._on_context_update(envelope)
        assert engine._detected_context_mode == "coding"
        assert engine._gaming_suppressed is False

    engine2 = ProactiveEngine()
    with patch("psutil.process_iter", return_value=[MockProcess("steam.exe")]), \
         patch("friday.core.fsm.cognitive_core.current_state", "IDLE"):
         
        envelope = EventEnvelope(
            topic="friday.system.context_update",
            priority=EventPriority.P3,
            source="system.context",
            correlation_id=uuid4(),
            session_id=uuid4(),
            payload={"active_window": "some title", "cpu_percent": 90.0, "memory_percent": 50.0}
        )
        
        await engine2._on_context_update(envelope)
        assert engine2._detected_context_mode == "gaming"
        assert engine2._gaming_suppressed is True

@pytest.mark.asyncio
async def test_low_disk_silent_trigger():
    from friday.core.proactive_engine import ProactiveEngine
    from friday.core.events import EventEnvelope, EventPriority
    from uuid import uuid4
    
    engine = ProactiveEngine()
    
    with patch("friday.core.fsm.cognitive_core.current_state", "IDLE"), \
         patch("psutil.process_iter", return_value=[]), \
         patch.object(engine, "_trigger_proactive") as mock_trigger:
         
        envelope = EventEnvelope(
            topic="friday.system.context_update",
            priority=EventPriority.P3,
            source="system.context",
            correlation_id=uuid4(),
            session_id=uuid4(),
            payload={
                "active_window": "idle", "cpu_percent": 10.0, "memory_percent": 50.0,
                "disk_partitions": [{"device": "C:", "free_percent": 5.0}],
                "cpu_temp": 45.0
            }
        )
        
        await engine._on_context_update(envelope)
        mock_trigger.assert_called_once()
        assert mock_trigger.call_args[0][0] == "LOW_DISK"

@pytest.mark.asyncio
async def test_high_cpu_temp_trigger():
    from friday.core.proactive_engine import ProactiveEngine
    from friday.core.events import EventEnvelope, EventPriority
    from uuid import uuid4
    
    engine = ProactiveEngine()
    
    with patch("friday.core.fsm.cognitive_core.current_state", "IDLE"), \
         patch("psutil.process_iter", return_value=[]), \
         patch.object(engine, "_trigger_proactive") as mock_trigger:
         
        envelope = EventEnvelope(
            topic="friday.system.context_update",
            priority=EventPriority.P3,
            source="system.context",
            correlation_id=uuid4(),
            session_id=uuid4(),
            payload={
                "active_window": "idle", "cpu_percent": 10.0, "memory_percent": 50.0,
                "disk_partitions": [{"device": "C:", "free_percent": 50.0}],
                "cpu_temp": 90.0
            }
        )
        
        await engine._on_context_update(envelope)
        mock_trigger.assert_called_once()
        assert mock_trigger.call_args[0][0] == "HIGH_CPU_TEMP"





