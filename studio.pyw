"""Supervisor latar belakang: nyalakan ComfyUI + app.py tanpa jendela, restart otomatis,
buka jendela app. Satu instance (lock socket di app_port+1). Hentikan: python studio.pyw --stop"""
import json, os, shutil, socket, subprocess, sys, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LOG = os.path.join(BASE, "studio.log")
PIDS = os.path.join(BASE, "studio.pids")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))


def cfg():
    c = {"app_port": 7860, "comfy_ports": [8188, 8000], "comfy_cmd": "", "comfy_cwd": "", "open_window": True}
    try:
        with open("studio_config.json", encoding="utf-8") as f:
            c.update(json.load(f))
    except (OSError, ValueError):
        pass
    return c


def comfy_alive(c):
    for p in c["comfy_ports"]:
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/system_stats" % p, timeout=2).read()
            return True
        except Exception:
            pass
    return False


def comfy_command(c):
    """Perintah menyalakan ComfyUI: dari config, atau deteksi otomatis."""
    if c["comfy_cmd"]:
        return c["comfy_cmd"], (c["comfy_cwd"] or None)
    local = os.environ.get("LOCALAPPDATA", "")
    for exe in (os.path.join(local, "Programs", "ComfyUI", "ComfyUI.exe"),
                os.path.join(local, "Programs", "@comfyorgcomfyui-electron", "ComfyUI.exe")):
        if os.path.exists(exe):
            return '"%s"' % exe, None
    for d in (c["comfy_cwd"], os.path.join(os.path.expanduser("~"), "ComfyUI"),
              os.path.join(os.path.expanduser("~"), "Documents", "ComfyUI"), "C:\\ComfyUI"):
        if d and os.path.exists(os.path.join(d, "main.py")):
            py = os.path.join(d, "venv", "Scripts", "python.exe")
            py = py if os.path.exists(py) else sys.executable.replace("pythonw", "python")
            return '"%s" main.py' % py, d
    return None, None


def stop():
    try:
        pids = [int(x) for x in open(PIDS).read().split()]
    except (OSError, ValueError):
        pids = []
    for pid in pids:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, creationflags=NOWIN)
        else:
            try:
                os.kill(pid, 15)
            except OSError:
                pass
    print("Dihentikan.")


def open_window(port):
    url = "http://127.0.0.1:%d" % port
    cands = [shutil.which("msedge"), shutil.which("chrome"),
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    for b in cands:
        if b and os.path.exists(b):
            subprocess.Popen([b, "--app=" + url], creationflags=NOWIN)
            return
    import webbrowser
    webbrowser.open(url)


def main():
    if "--stop" in sys.argv:
        return stop()
    c = cfg()
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", c["app_port"] + 1))
    except OSError:  # sudah jalan: cukup buka jendela
        if "--background" not in sys.argv and c["open_window"]:
            open_window(c["app_port"])
        return
    log("studio start")
    comfy = app = None
    opened = False
    try:
        while True:
            if not comfy_alive(c) and (comfy is None or comfy.poll() is not None):
                cmd, cwd = comfy_command(c)
                if cmd:
                    log("start comfy: " + cmd)
                    comfy = subprocess.Popen(cmd, cwd=cwd, shell=True, creationflags=NOWIN,
                                             stdout=open(LOG, "a"), stderr=subprocess.STDOUT)
                else:
                    log("ComfyUI tidak ditemukan; isi comfy_cmd di studio_config.json")
            if app is None or app.poll() is not None:
                log("start app.py")
                exe = sys.executable.replace("pythonw", "python") if os.name == "nt" else sys.executable
                app = subprocess.Popen([exe, "app.py"], creationflags=NOWIN,
                                       stdout=open(LOG, "a"), stderr=subprocess.STDOUT)
            with open(PIDS, "w") as f:
                f.write(" ".join(str(p.pid) for p in (comfy, app) if p) + " %d" % os.getpid())
            if not opened and c["open_window"] and "--background" not in sys.argv:
                time.sleep(1.5)
                open_window(c["app_port"])
                opened = True
            time.sleep(5)
    finally:
        for p in (comfy, app):
            if p and p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
