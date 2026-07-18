import os
import psutil

lock_file = r"C:\FRIDAY\backend\data\qdrant\.lock"
if os.path.exists(lock_file):
    print(f"Lock file exists. Size: {os.path.getsize(lock_file)}")
    # Try to find which process has it open using psutil
    for proc in psutil.process_iter(['pid', 'name', 'open_files']):
        try:
            for f in proc.info.get('open_files') or []:
                if lock_file.lower() in f.path.lower():
                    print(f"Process holding lock: PID={proc.info['pid']}, Name={proc.info['name']}")
        except Exception:
            pass
else:
    print("Lock file does not exist.")
