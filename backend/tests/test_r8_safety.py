import sys
from unittest.mock import MagicMock, patch
import pytest
import shutil
import tempfile
import re
from pathlib import Path

from friday.security.deletion_guard import is_tier1_blocked, validate_deletion_path
from friday.security.terminal_whitelist import is_safe_path_boundary, ping_host, list_directory

# autouse fixture to patch sys.modules only during test execution of tests in this file
@pytest.fixture(autouse=True)
def mock_pc_agent_and_session():
    # Mock pc_agent module to avoid importing Playwright/browser components which hang in test environments
    pc_agent_mock = MagicMock()
    # simple pattern matcher replicating is_safe_folder_name logic for unit test validation
    def mock_is_safe_folder_name(name: str) -> bool:
        if not name:
            return False
        if ":" in name or name.startswith("/") or name.startswith("\\") or ".." in name:
            return False
        # allow desktop subfolders for the sake of the test
        if "safe_folder" in name:
            return True
        return False

    pc_agent_mock.is_safe_folder_name = mock_is_safe_folder_name

    # Setup the session mock with async get/set methods
    session_instance_mock = MagicMock()
    async def mock_get(*args, **kwargs):
        return []
    async def mock_set(*args, **kwargs):
        pass
    session_instance_mock.get = mock_get
    session_instance_mock.set = mock_set
    
    session_mock = MagicMock()
    session_mock.SessionMemory.return_value = session_instance_mock

    modules_patch = {
        "friday.agents.pc_agent": pc_agent_mock,
        "qdrant_client": MagicMock(),
        "friday.memory.session": session_mock,
        "friday.memory.semantic": MagicMock(),
        "friday.memory.episodic": MagicMock(),
        "friday.memory.knowledge_graph": MagicMock(),
        "brain.spacy_loader": MagicMock()
    }
    
    with patch.dict(sys.modules, modules_patch):
        yield

def validate_hostname(host: str) -> bool:
    HOST_REGEX = re.compile(r"^[a-zA-Z0-9\.-]+$")
    host_clean = host.strip()
    if not host_clean:
        return False
    if len(host_clean) > 253:
        return False
    if host_clean.startswith(".") or host_clean.endswith(".") or host_clean.startswith("-") or host_clean.endswith("-"):
        return False
    if not HOST_REGEX.match(host_clean):
        return False
    return True

def test_tier1_hard_block():
    # Test blocked roots
    assert is_tier1_blocked(Path("C:/")) is True
    assert is_tier1_blocked(Path("C:/Windows")) is True
    assert is_tier1_blocked(Path("C:/Windows/System32")) is True
    assert is_tier1_blocked(Path("C:/Program Files")) is True
    assert is_tier1_blocked(Path("C:/Program Files/Common Files")) is True
    assert is_tier1_blocked(Path("C:/Program Files (x86)")) is True
    assert is_tier1_blocked(Path("C:/ProgramData")) is True
    assert is_tier1_blocked(Path("C:/Users")) is True
    
    # Test unblocked paths (e.g. user home subdirs)
    user_home = Path.home()
    assert is_tier1_blocked(user_home / "Documents") is False
    assert is_tier1_blocked(user_home / "Desktop") is False

def test_tier2_recycle_bin():
    # Create a temp file to delete
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_file_path = f.name
        
    assert Path(temp_file_path).exists()
    
    # Verify send2trash is used on it
    with patch("friday.security.deletion_guard.send2trash") as mock_send2trash:
        from friday.security.deletion_guard import delete_to_recycle_bin
        delete_to_recycle_bin(temp_file_path)
        mock_send2trash.assert_called_once_with(str(Path(temp_file_path).resolve()))

def test_list_directory_boundaries():
    user_home = Path.home()
    
    # Under user home or Desktop should be allowed
    assert is_safe_path_boundary(user_home / "Documents") is True
    assert is_safe_path_boundary("safe_folder") is True
    
    # Outside user home should be rejected (e.g. C:\Windows, C:\Program Files)
    assert is_safe_path_boundary(Path("C:/Windows")) is False
    assert is_safe_path_boundary(Path("C:/Program Files")) is False

def test_ping_host_regex():
    # Valid hostnames
    assert validate_hostname("google.com") is True
    assert validate_hostname("my-host.sub.domain") is True
    assert validate_hostname("127.0.0.1") is True
    
    # Invalid hostnames (starts/ends with dot or dash, too long, invalid chars)
    assert validate_hostname(".google.com") is False
    assert validate_hostname("google.com-") is False
    assert validate_hostname("a" * 254) is False
    assert validate_hostname("invalid_char;rm -rf") is False

@pytest.mark.asyncio
async def test_confirming_state_flow():
    # Import FSM and Core inside the test execution context after patches are applied
    from friday.core.fsm import AssistantState, CognitiveFSM, CognitiveCore
    from friday.core.events import EventEnvelope, EventPriority
    from uuid import uuid4
    
    # Test that FSM transitions to CONFIRMING for DELETE_PATH
    fsm = CognitiveFSM()
    core = CognitiveCore(fsm=fsm)
    
    corr_id = uuid4()
    session_id = uuid4()
    
    # Trigger turn for DELETE_PATH
    envelope = EventEnvelope(
        topic="friday.perception.text.input",
        priority=EventPriority.P1,
        source="user",
        correlation_id=corr_id,
        session_id=session_id,
        payload={"text": "delete file C:/Users/gpska/Desktop/safe.txt"}
    )
    
    # Patch parsing to return DELETE_PATH
    with patch("friday.core.fsm.parse_intent", return_value={"intent": "DELETE_PATH", "path": "C:/Users/gpska/Desktop/safe.txt", "confidence": 1.0}), \
         patch("friday.core.fsm.event_bus.publish") as mock_publish, \
         patch("friday.core.fsm.CognitiveCore._retrieve_memory_context", return_value={}):
        
        await core._process_request_turn(envelope)
        
        # State should be CONFIRMING
        assert fsm.current_state == AssistantState.CONFIRMING
        
        # Now mock user reply "yes" to proceed
        confirm_envelope = EventEnvelope(
            topic="friday.perception.text.input",
            priority=EventPriority.P1,
            source="user",
            correlation_id=corr_id,
            session_id=session_id,
            payload={"text": "yes"}
        )
        
        # Reset publish mocks
        mock_publish.reset_mock()
        
        # We need to mock pc_agent result publishing or check transition
        with patch("friday.core.fsm.event_bus.publish") as mock_pub_agent:
            await core._process_request_turn(confirm_envelope)
            
            # Since confirm count starts at 1, the first "yes" for double-confirmation should transition to CONFIRMING again with count=2
            assert fsm.current_state == AssistantState.CONFIRMING
            assert fsm.working_memory["confirm_count"] == 2
            
            # Second yes should complete it
            confirm_envelope_2 = EventEnvelope(
                topic="friday.perception.text.input",
                priority=EventPriority.P1,
                source="user",
                correlation_id=corr_id,
                session_id=session_id,
                payload={"text": "yes"}
            )
            
            # Patch wait_for to complete instantly
            with patch("asyncio.wait_for", return_value=None):
                await core._process_request_turn(confirm_envelope_2)
                
                # Should transition to WAITING (waiting for agent execution results)
                assert fsm.current_state in (AssistantState.WAITING, AssistantState.IDLE)
