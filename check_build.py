import os
import sys

def get_latest_mod_time():
    latest_time = 0.0
    
    # Folders to scan and file patterns to match
    scan_paths = [
        ("backend", [".py"]),
        ("frontend/src", [".ts", ".tsx", ".css", ".html", ".js", ".json"]),
        ("frontend/electron", [".js", ".cjs", ".ts", ".json"]),
    ]
    
    # Specific files to scan in root/frontend root
    specific_files = [
        "frontend/package.json",
        "frontend/vite.config.ts",
        "frontend/index.html",
    ]
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    for rel_dir, extensions in scan_paths:
        dir_path = os.path.join(base_dir, rel_dir)
        if not os.path.exists(dir_path):
            continue
        for root, dirs, files in os.walk(dir_path):
            # Exclude pycaches
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            if ".pytest_cache" in dirs:
                dirs.remove(".pytest_cache")
                
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in extensions:
                    file_path = os.path.join(root, file)
                    try:
                        mtime = os.path.getmtime(file_path)
                        if mtime > latest_time:
                            latest_time = mtime
                    except Exception:
                        pass
                        
    for rel_file in specific_files:
        file_path = os.path.join(base_dir, rel_file)
        if os.path.exists(file_path):
            try:
                mtime = os.path.getmtime(file_path)
                if mtime > latest_time:
                    latest_time = mtime
            except Exception:
                pass
                
    return latest_time

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # ── Phase 6.2: Environment Config Validation ─────────────────────────────
    root_env_path = os.path.join(base_dir, ".env")
    if os.path.exists(root_env_path):
        print(f"[CHECK_BUILD] Validating root environment config: {root_env_path}")
        with open(root_env_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        env_vars = {}
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()
                
        groq_key = env_vars.get("GROQ_API_KEY", "")
        if not groq_key:
            print("[ERROR] Build validation failed: GROQ_API_KEY is missing or empty in .env!")
            sys.exit(1)
        if groq_key.startswith("your_") or "placeholder" in groq_key.lower() or len(groq_key) < 10:
            print(f"[ERROR] Build validation failed: GROQ_API_KEY contains an invalid or placeholder value: '{groq_key}'!")
            sys.exit(1)
        print("[CHECK_BUILD] Root environment variables validated successfully.")
        
    exe_path = os.path.join(base_dir, "frontend", "dist-electron", "FRIDAY-win32-x64", "FRIDAY.exe")
    
    if not os.path.exists(exe_path):
        # Exe doesn't exist, must build!
        print("[CHECK_BUILD] Official executable not found. Build is required.")
        sys.exit(1)
        
    try:
        exe_time = os.path.getmtime(exe_path)
    except Exception:
        print("[CHECK_BUILD] Error getting executable timestamp. Rebuilding just in case.")
        sys.exit(1)
        
    latest_src_time = get_latest_mod_time()
    
    if latest_src_time > exe_time:
        print(f"[CHECK_BUILD] Source code has been updated since last build. Recompile required.")
        sys.exit(1)
    else:
        print("[CHECK_BUILD] Executable is fully up-to-date with source code.")
        sys.exit(0)

if __name__ == "__main__":
    main()
