# backend/friday/tools/mcp_schemas.py

MCP_TOOL_REGISTRY = [
    {
        "name": "web_search",
        "description": "Search the web for information using a query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "search query"}
            },
            "required": ["query"]
        },
        "permission_level": "ELEVATED"
    },
    {
        "name": "browser_open",
        "description": "Open a browser window and navigate to a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to open"}
            },
            "required": ["url"]
        },
        "permission_level": "ELEVATED"
    },
    {
        "name": "file_read",
        "description": "Read the contents of a file from a safe path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to read the file from"}
            },
            "required": ["path"]
        },
        "permission_level": "READ_ONLY"
    },
    {
        "name": "file_write",
        "description": "Write or overwrite contents of a file at a safe path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write the file to"},
                "content": {"type": "string", "description": "Content to write"}
            },
            "required": ["path", "content"]
        },
        "permission_level": "WRITE_SAFE"
    },
    {
        "name": "file_delete",
        "description": "Delete a file or directory at a safe path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to delete"}
            },
            "required": ["path"]
        },
        "permission_level": "PRIVILEGED"
    },
    {
        "name": "app_open",
        "description": "Launch an application.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "Name or path of application to open"}
            },
            "required": ["app"]
        },
        "permission_level": "ELEVATED"
    },
    {
        "name": "app_close",
        "description": "Close an application.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "Name of application to close"}
            },
            "required": ["app"]
        },
        "permission_level": "ELEVATED"
    },
    {
        "name": "system_status",
        "description": "Get current system status (CPU, RAM, active window, battery).",
        "input_schema": {
            "type": "object",
            "properties": {}
        },
        "permission_level": "READ_ONLY"
    },
    {
        "name": "set_reminder",
        "description": "Set a reminder at a specific time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Reminder content"},
                "time": {"type": "string", "description": "Time to trigger reminder"}
            },
            "required": ["text", "time"]
        },
        "permission_level": "ELEVATED"
    },
    {
        "name": "screenshot",
        "description": "Capture a screenshot of the current screen.",
        "input_schema": {
            "type": "object",
            "properties": {}
        },
        "permission_level": "READ_ONLY"
    },
    {
        "name": "clipboard_read",
        "description": "Read the current text from the clipboard.",
        "input_schema": {
            "type": "object",
            "properties": {}
        },
        "permission_level": "READ_ONLY"
    },
    {
        "name": "clipboard_write",
        "description": "Write text into the clipboard.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to write into the clipboard"}
            },
            "required": ["text"]
        },
        "permission_level": "WRITE_SAFE"
    }
]
