import os
import asyncio
import subprocess
from loguru import logger

class Sandbox:
    def __init__(self, sandbox_root: str = None):
        if sandbox_root is None:
            self.sandbox_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "sandbox"))
        else:
            self.sandbox_root = os.path.abspath(sandbox_root)
        os.makedirs(self.sandbox_root, exist_ok=True)

    def _validate_path(self, path: str) -> str:
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(self.sandbox_root):
            raise PermissionError(f"[Sandbox] Access denied. Path '{abs_path}' is outside the sandbox root '{self.sandbox_root}'.")
        return abs_path

    async def write_safe_file(self, filepath: str, content: str) -> str:
        safe_path = self._validate_path(filepath)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        
        loop = asyncio.get_running_loop()
        def _write():
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
        await loop.run_in_executor(None, _write)
        logger.info(f"[Sandbox] Safely wrote file: {safe_path}")
        return safe_path

    async def execute_safe_command(self, cmd_line: str, cwd: str = None) -> dict:
        workdir = cwd or self.sandbox_root
        safe_workdir = self._validate_path(workdir)

        forbidden_commands = ["rm -rf /", "rmdir /s", "del /f /s /q c:", "format", "mkfs"]
        cmd_lower = cmd_line.lower()
        if any(f_cmd in cmd_lower for f_cmd in forbidden_commands):
            raise PermissionError(f"[Sandbox] Command contains forbidden dangerous patterns.")

        logger.info(f"[Sandbox] Executing command: '{cmd_line}' in {safe_workdir}")
        
        process = await asyncio.create_subprocess_shell(
            cmd_line,
            cwd=safe_workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        return {
            "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace")
        }

# Global Sandbox instance
sandbox = Sandbox()
