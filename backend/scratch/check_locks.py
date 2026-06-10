import psutil
import os

current_pid = os.getpid()
print(f"Current agent PID: {current_pid}")

for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if 'python' in proc.info['name'].lower():
            if proc.info['pid'] != current_pid:
                print(f"Other Python process: PID={proc.info['pid']}, Name={proc.info['name']}, Cmdline={proc.info['cmdline']}")
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
