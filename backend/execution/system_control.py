import os

import shutil

import psutil

def get_system_status():

    cpu = psutil.cpu_percent()

    ram = psutil.virtual_memory().percent

    disk = shutil.disk_usage("C:")

    free = disk.free // (1024 ** 3)

    return (

        f"CPU usage is {cpu} percent "

        f"RAM usage is {ram} percent "

        f"and {free} GB is free on drive C"

    )

def clear_temp():

    paths = [

        os.environ.get("TEMP"),

        "C:\\Windows\\Temp"
    ]

    for path in paths:

        if not path:
            continue

        if not os.path.exists(path):
            continue

        for item in os.listdir(path):

            try:

                full = os.path.join(path, item)

                if os.path.isfile(full):

                    os.unlink(full)

                elif os.path.isdir(full):

                    shutil.rmtree(full)

            except:
                pass

def shutdown_pc():

    os.system(
        "shutdown /s /t 1"
    )

def restart_pc():

    os.system(
        "shutdown /r /t 1"
    )

def lock_pc():

    os.system(
        "rundll32.exe user32.dll,LockWorkStation"
    )

def sleep_pc():

    os.system(
        "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"
    )