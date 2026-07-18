import psutil
import platform
import time
from typing import Dict, Any, List

def get_system_status_full() -> Dict[str, Any]:
    """
    Assembles a comprehensive system resource usage and status dictionary.
    Excludes destructive actions. Completely read-only.
    """
    # 1. CPU Info
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count_logical = psutil.cpu_count(logical=True)
    cpu_count_physical = psutil.cpu_count(logical=False)
    cpu_freq = psutil.cpu_freq()
    cpu_freq_mhz = cpu_freq.current if cpu_freq else 0.0

    # 2. Virtual Memory
    vm = psutil.virtual_memory()
    memory_total_gb = vm.total / (1024 ** 3)
    memory_used_gb = vm.used / (1024 ** 3)
    memory_percent = vm.percent

    # 3. Disk Space (C:\ drive specifically and others)
    disk_partitions = []
    for partition in psutil.disk_partitions():
        if 'cdrom' in partition.opts or not partition.mountpoint:
            continue
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disk_partitions.append({
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "total_gb": round(usage.total / (1024 ** 3), 1),
                "used_gb": round(usage.used / (1024 ** 3), 1),
                "free_gb": round(usage.free / (1024 ** 3), 1),
                "percent": usage.percent
            })
        except PermissionError:
            continue
        except OSError:
            continue

    # 4. OS and Platform details
    os_info = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
        "uptime": round(time.time() - psutil.boot_time())
    }

    # 5. Top memory-consuming processes
    process_list = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            info = proc.info
            info['cpu_percent'] = info.get('cpu_percent') or 0.0
            info['memory_percent'] = info.get('memory_percent') or 0.0
            process_list.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # Sort by memory percent and take top 10
    top_processes = sorted(process_list, key=lambda x: x['memory_percent'], reverse=True)[:10]

    # 6. Battery Info
    battery_info = None
    try:
        battery = psutil.sensors_battery()
        if battery:
            battery_info = {
                "percent": float(battery.percent),
                "power_plugged": bool(battery.power_plugged),
                "secsleft": int(battery.secsleft) if battery.secsleft is not None else -1
            }
    except Exception:
        pass

    # 7. CPU Temperature
    cpu_temp = None
    try:
        temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else None
        if temps:
            cpu_temps = []
            for name, entries in temps.items():
                if "cpu" in name.lower() or "core" in name.lower():
                    for entry in entries:
                        cpu_temps.append(entry.current)
            if cpu_temps:
                cpu_temp = sum(cpu_temps) / len(cpu_temps)
    except Exception:
        pass

    return {
        "cpu": {
            "percent": cpu_percent,
            "logical_cores": cpu_count_logical,
            "physical_cores": cpu_count_physical,
            "frequency_mhz": round(cpu_freq_mhz, 1),
            "temperature": round(cpu_temp, 1) if cpu_temp is not None else None
        },
        "memory": {
            "total_gb": round(memory_total_gb, 1),
            "used_gb": round(memory_used_gb, 1),
            "percent": memory_percent
        },
        "disks": disk_partitions,
        "os": os_info,
        "top_processes": top_processes,
        "battery": battery_info
    }
