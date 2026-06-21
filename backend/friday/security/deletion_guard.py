import os
from pathlib import Path
from loguru import logger
from send2trash import send2trash

# Hardcoded absolute blocked paths for Tier 1 protection
BLOCKED_SYSTEM_PATHS = {
    Path("C:/Windows").resolve(),
    Path("C:/Program Files").resolve(),
    Path("C:/Program Files (x86)").resolve(),
    Path("C:/ProgramData").resolve(),
}

def is_tier1_blocked(path: Path) -> bool:
    """
    Checks if a path is a Tier 1 blocked critical system path.
    """
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path.absolute()
        
    # Check if resolved is exactly C:\ or C:\Users
    if resolved == Path("C:/").resolve() or resolved == Path("C:/Users").resolve():
        return True
        
    # Check if resolved path is in BLOCKED_SYSTEM_PATHS or under them
    for root in BLOCKED_SYSTEM_PATHS:
        if resolved == root or root in resolved.parents:
            return True
            
    return False

def validate_deletion_path(path_str: str) -> Path:
    """
    Resolves and validates that the path is not a critical system path (Tier 1).
    Raises PermissionError if a Tier 1 path is targeted.
    """
    if not path_str:
        raise ValueError("Empty deletion path targeted.")

    resolved_path = Path(path_str).resolve()
    
    # Tier 1 protection check
    if is_tier1_blocked(resolved_path):
        raise PermissionError(f"Access Denied: Unconditional block on deleting critical system path '{resolved_path}' (Tier 1).")

    # Ensure it exists on disk
    if not resolved_path.exists():
        raise FileNotFoundError(f"Target path does not exist on disk: {resolved_path}")

    return resolved_path

def delete_to_recycle_bin(path_str: str) -> bool:
    """
    Executes deletion using send2trash (Tier 2).
    Returns True if successful, raises exceptions on errors.
    """
    resolved_path = validate_deletion_path(path_str)
    
    logger.info(f"[DELETION_GUARD] Moving path to Recycle Bin: {resolved_path}")
    send2trash(str(resolved_path))
    return True

def clean_temp_files() -> dict:
    """
    Cleans up the user's temporary files directory (%TEMP%) by moving files to the Recycle Bin.
    Routes each file/folder through the deletion guard.
    """
    temp_dir_str = os.environ.get('TEMP') or os.environ.get('TMP')
    if not temp_dir_str:
        return {"success": False, "error": "TEMP environment variable not found."}
        
    temp_dir = Path(temp_dir_str).resolve()
    logger.info(f"[DELETION_GUARD] Starting temp file cleanup for: {temp_dir}")
    
    success_count = 0
    fail_count = 0
    errors = []
    
    try:
        for entry in os.scandir(temp_dir):
            entry_path = Path(entry.path)
            try:
                # Check Tier 1 block
                if is_tier1_blocked(entry_path):
                    continue
                # Move to recycle bin
                send2trash(str(entry_path))
                success_count += 1
            except Exception as e:
                # Locked files/folders are common, log and keep going
                fail_count += 1
                errors.append(f"{entry_path.name}: {str(e)}")
    except Exception as e:
        return {"success": False, "error": str(e)}
        
    return {
        "success": True,
        "success_count": success_count,
        "fail_count": fail_count,
        "errors_sample": errors[:5]
    }
