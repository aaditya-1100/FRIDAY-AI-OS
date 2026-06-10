from typing import Dict, List
from friday.core.events import AgentType, AgentTrustLevel, PermissionEnum

AGENT_TRUST_MAP: Dict[AgentType, AgentTrustLevel] = {
    AgentType.VOICE_AGENT: AgentTrustLevel.SYSTEM,
    AgentType.MEMORY_AGENT: AgentTrustLevel.SYSTEM,
    AgentType.KNOWLEDGE_AGENT: AgentTrustLevel.ELEVATED,
    AgentType.PC_AGENT: AgentTrustLevel.STANDARD,
    AgentType.WEB_AGENT: AgentTrustLevel.STANDARD
}

TOOL_PERMISSION_MAP: Dict[str, PermissionEnum] = {
    "READ_MEMORY": PermissionEnum.READ_ONLY,
    "RETRIEVE_SEMANTIC": PermissionEnum.READ_ONLY,
    "QUERY_GRAPH": PermissionEnum.READ_ONLY,
    "LIST_REMINDERS": PermissionEnum.READ_ONLY,
    "SYSTEM_STATUS": PermissionEnum.READ_ONLY,
    "SCREENSHOT": PermissionEnum.READ_ONLY,
    "SCREEN_UNDERSTANDING": PermissionEnum.READ_ONLY,
    "FILE_READ": PermissionEnum.READ_ONLY,
    "CLIPBOARD_READ": PermissionEnum.READ_ONLY,
    "WINDOW_LIST": PermissionEnum.READ_ONLY,
    "BROWSER_SCREENSHOT": PermissionEnum.READ_ONLY,

    "WRITE_MEMORY": PermissionEnum.WRITE_SAFE,
    "ADD_FACT": PermissionEnum.WRITE_SAFE,
    "ADD_RELATION": PermissionEnum.WRITE_SAFE,
    "LOAD_SESSION_CONTEXT": PermissionEnum.WRITE_SAFE,
    "FILE_WRITE": PermissionEnum.WRITE_SAFE,
    "FILE_CREATE": PermissionEnum.WRITE_SAFE,
    "FILE_MOVE": PermissionEnum.WRITE_SAFE,
    "CLIPBOARD_WRITE": PermissionEnum.WRITE_SAFE,

    "SPOTIFY_CONTROL": PermissionEnum.ELEVATED,
    "SET_REMINDER": PermissionEnum.ELEVATED,
    "SET_TIMER": PermissionEnum.ELEVATED,
    "SET_ALARM": PermissionEnum.ELEVATED,
    "SET_SCHEDULED_TASK": PermissionEnum.ELEVATED,
    "SET_RECURRING_REMINDER": PermissionEnum.ELEVATED,
    "STOPWATCH_CONTROL": PermissionEnum.ELEVATED,
    "CANCEL_REMINDER": PermissionEnum.ELEVATED,
    "WEB_SEARCH": PermissionEnum.ELEVATED,
    "WEB_SCRAPE": PermissionEnum.ELEVATED,
    "WINDOW_CONTROL": PermissionEnum.ELEVATED,
    "OPEN": PermissionEnum.ELEVATED,
    "APP_CLOSE": PermissionEnum.ELEVATED,
    "APP_FOCUS": PermissionEnum.ELEVATED,
    "BROWSER_OPEN": PermissionEnum.ELEVATED,
    "BROWSER_SEARCH": PermissionEnum.ELEVATED,
    "BROWSER_CLICK": PermissionEnum.ELEVATED,
    "BROWSER_CLOSE": PermissionEnum.ELEVATED,

    "SHELL_EXECUTE": PermissionEnum.PRIVILEGED,
    "FILE_DELETE": PermissionEnum.PRIVILEGED,
    "BROWSER_FILL": PermissionEnum.PRIVILEGED,

    "SYSTEM_SHUTDOWN": PermissionEnum.HUMAN_CONFIRMED,
    "SYSTEM_RESTART": PermissionEnum.HUMAN_CONFIRMED,
    "SEND_EMAIL": PermissionEnum.HUMAN_CONFIRMED,
    "PURCHASE": PermissionEnum.HUMAN_CONFIRMED,
    "EXTERNAL_POST": PermissionEnum.HUMAN_CONFIRMED
}

TRUST_LIMIT_MAP: Dict[AgentTrustLevel, PermissionEnum] = {
    AgentTrustLevel.SYSTEM: PermissionEnum.HUMAN_CONFIRMED,
    AgentTrustLevel.ELEVATED: PermissionEnum.PRIVILEGED,
    AgentTrustLevel.STANDARD: PermissionEnum.ELEVATED,
    AgentTrustLevel.SANDBOXED: PermissionEnum.READ_ONLY
}
