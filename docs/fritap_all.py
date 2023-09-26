# fritap_all.py: attach fritap to all subprocesses of a specific executable on windows
# make sure to install pywin32, psutil, frida, fritap first

import psutil
import subprocess
import atexit
import win32api
import win32con

PROCNAME = "CiscoJabber.exe"

processes = []
for proc in psutil.process_iter():
    if proc.name() == PROCNAME:
        print("Jabber PID:", proc.pid)
        p = subprocess.Popen([
            "friTap.exe",
            "--pcap", f"{proc.pid}.pcap",
            f"{proc.pid}"
            # "-k", f"{proc.pid}.keys"  - logging keys is only supported on linux
        ])
        processes.append(p)
        print("Frida PID:", p.pid)
        print()

def win_kill(pid):
    hProc = None
    try:
        hProc = win32api.OpenProcess(win32con.PROCESS_TERMINATE, 0, pid)
        win32api.TerminateProcess(hProc, 0)
    except Exception:
        return False
    finally:
        if hProc != None:
            hProc.Close()
    return True

def cleanup():
    for p in processes:
        print("KILL", p, win_kill(p.pid))

# kill frida instances before exiting the script
atexit.register(cleanup)

# wait for CTRL+C until everything of interest was captured
input("wait...")
exit()
