import os
import re
import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any
import psutil

# Character class for hostname validation
HOST_REGEX = re.compile(r"^[a-zA-Z0-9\.-]+$")

def is_safe_path_boundary(path_input) -> bool:
    """
    Validates that a resolved path lies strictly under the user's home directory tree
    or is validated by the existing is_safe_folder_name pattern from pc_agent.py.
    """
    try:
        path_str = str(path_input)
        # Reuse helper from pc_agent.py to keep consistency
        from friday.agents.pc_agent import is_safe_folder_name
        if is_safe_folder_name(path_str):
            return True
            
        resolved = Path(path_str).resolve()
        home = Path.home().resolve()
        return home == resolved or home in resolved.parents
    except Exception:
        return False

def check_disk_space() -> str:
    """Native Python implementation of disk space checking using psutil."""
    try:
        partitions = psutil.disk_partitions()
        lines = []
        for p in partitions:
            if 'cdrom' in p.opts or not p.mountpoint:
                continue
            try:
                usage = psutil.disk_usage(p.mountpoint)
                total_gb = usage.total / (1024 ** 3)
                used_gb = usage.used / (1024 ** 3)
                free_gb = usage.free / (1024 ** 3)
                percent = usage.percent
                lines.append(
                    f"Drive {p.device} ({p.mountpoint}): Total={total_gb:.1f}GB, Used={used_gb:.1f}GB ({percent}%), Free={free_gb:.1f}GB"
                )
            except PermissionError:
                continue
            except OSError:
                continue
        return "\n".join(lines) if lines else "No accessible drives found."
    except Exception as e:
        return f"Error checking disk space: {e}"

def check_system_info() -> str:
    """Native Python implementation of system information using platform and psutil."""
    try:
        mem = psutil.virtual_memory()
        total_mem_gb = mem.total / (1024 ** 3)
        available_mem_gb = mem.available / (1024 ** 3)
        
        info = [
            f"OS: {platform.system()} {platform.release()} (Version: {platform.version()})",
            f"Architecture: {platform.machine()}",
            f"Processor: {platform.processor()}",
            f"Physical CPU Cores: {psutil.cpu_count(logical=False)}",
            f"Logical CPU Cores: {psutil.cpu_count(logical=True)}",
            f"Memory: Total={total_mem_gb:.1f}GB, Available={available_mem_gb:.1f}GB ({mem.percent}% used)",
            f"Python Version: {platform.python_version()}"
        ]
        return "\n".join(info)
    except Exception as e:
        return f"Error retrieving system info: {e}"

def list_processes() -> str:
    """Native Python implementation of process listing using psutil."""
    try:
        processes = []
        # Sort by memory percent descending, limit to top 15
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                # Avoid processes with None values
                info['cpu_percent'] = info.get('cpu_percent') or 0.0
                info['memory_percent'] = info.get('memory_percent') or 0.0
                processes.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        processes = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:15]
        
        lines = [f"{'PID':<8}{'Name':<25}{'User':<20}{'CPU%':<8}{'MEM%':<8}"]
        lines.append("-" * 69)
        for p in processes:
            lines.append(f"{p['pid']:<8}{p['name'][:24]:<25}{str(p['username'])[:19]:<20}{p['cpu_percent']:<8.1f}{p['memory_percent']:<8.1f}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing processes: {e}"

def ping_host(host: str) -> str:
    """Executes a ping command with strict validation on hostname."""
    host_clean = host.strip()
    if not host_clean:
        raise ValueError("Ping targeted at empty host.")
    
    # 1. Validation checks
    if len(host_clean) > 253:
        raise ValueError("Hostname exceeds maximum length of 253 characters.")
    if host_clean.startswith(".") or host_clean.endswith(".") or host_clean.startswith("-") or host_clean.endswith("-"):
        raise ValueError("Hostname cannot start or end with dots or dashes.")
    if not HOST_REGEX.match(host_clean):
        raise ValueError(f"Hostname contains invalid characters or malformed pattern: '{host_clean}'")

    # 2. Execution
    try:
        # Run standard OS ping
        cmd = ["ping", "-n", "4", host_clean] if sys.platform == "win32" else ["ping", "-c", "4", host_clean]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10.0)
        return res.stdout if res.returncode == 0 else f"Ping failed:\n{res.stdout}\n{res.stderr}"
    except subprocess.TimeoutExpired:
        return "Ping request timed out."
    except Exception as e:
        return f"Ping execution error: {e}"

def list_directory(path_str: str) -> str:
    """Lists directory contents with strict root-boundary checks."""
    if not path_str:
        raise ValueError("Directory path cannot be empty.")

    path_obj = Path(path_str)
    # Enforce boundary check
    if not is_safe_path_boundary(path_obj):
        raise PermissionError(f"Access Denied: Path '{path_str}' falls outside the allowed user home directory tree.")

    resolved_path = path_obj.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Target directory does not exist: {resolved_path}")
    if not resolved_path.is_dir():
        raise ValueError(f"Target path is a file, not a directory: {resolved_path}")

    try:
        contents = []
        for entry in os.scandir(resolved_path):
            info = entry.stat()
            size_kb = info.st_size / 1024
            mod_time = entry.stat().st_mtime
            import datetime
            time_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M')
            kind = "DIR" if entry.is_dir() else "FILE"
            contents.append(f"{time_str:<18}{kind:<8}{size_kb:<10.1f}{entry.name}")
        
        lines = [f"Directory listing of: {resolved_path}", f"{'Last Modified':<18}{'Type':<8}{'Size(KB)':<10}{'Name'}"]
        lines.append("-" * 60)
        lines.extend(contents)
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing directory: {e}"

# Terminal Whitelist Dispatcher Registry
WHITELISTED_COMMANDS = {
    "CHECK_DISK_SPACE": lambda params: check_disk_space(),
    "CHECK_SYSTEM_INFO": lambda params: check_system_info(),
    "LIST_PROCESSES": lambda params: list_processes(),
    "PING_HOST": lambda params: ping_host(params.get("host", "")),
    "LIST_DIRECTORY": lambda params: list_directory(params.get("path", ""))
}

def execute_whitelisted_command(key: str, params: dict = None) -> str:
    """
    Validates and executes a command from the whitelist by key name.
    """
    if key not in WHITELISTED_COMMANDS:
        raise ValueError(f"Requested command '{key}' is not in the approved terminal command whitelist.")
    
    cmd_fn = WHITELISTED_COMMANDS[key]
    return cmd_fn(params or {})
