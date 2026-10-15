"""Supervisor latar belakang: nyalakan ComfyUI + app.py tanpa jendela, restart otomatis,
buka jendela app, pasang pembaruan otomatis dari GitHub. Satu instance (lock socket di app_port+1).
Hentikan: python studio.pyw --stop"""
import json, os, shutil, socket, subprocess, sys, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)
import comfy_detect
import updater
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LOG = os.path.join(BASE, "studio.log")
PIDS = os.path.join(BASE, "studio.pids")
SELF_FILES = {"studio.pyw", "updater.py", "comfy_detect.py"}  # berubah -> supervisor ikut restart


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def rotate_log():
    try:
        if os.path.getsize(LOG) > 5 * 1024 * 1024:  # output ComfyUI ikut masuk; jangan sampai membengkak
            os.replace(LOG, LOG + ".old")
    except OSError:
        pass


def cfg():
    c = {"app_port": 7860, "comfy_ports": [8188, 8000], "comfy_cmd": "", "comfy_cwd": "", "open_window": True,
         "auto_update": True, "update_check_hours": 3}
    try:
        with open("studio_config.json", encoding="utf-8") as f:
            c.update(json.load(f))
    except (OSError, ValueError):
        pass
    return c


def comfy_alive(c):
    """Port ComfyUI terbuka = hidup. Jangan menunggu jawaban HTTP: saat generate/memuat model ComfyUI bisa
    lambat menjawab, dan dulu itu dianggap mati sehingga ComfyUI kedua dinyalakan berulang-ulang."""
    for p in c["comfy_ports"]:
        try:
            socket.create_connection(("127.0.0.1", int(p)), timeout=1).close()
            return True
        except (OSError, ValueError):
            pass
    return False


def app_busy(port):
    """True bila app sedang mengerjakan job / menulis; pembaruan ditunda."""
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/api/busy" % port, headers={"X-Studio": "1"})
        return bool(json.loads(urllib.request.urlopen(req, timeout=5).read().decode()).get("busy"))
    except Exception:
        return False


def kill(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, creationflags=NOWIN)
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def stop():
    try:
        pids = [int(x) for x in open(PIDS).read().split()]
    except (OSError, ValueError):
        pids = []
    for pid in pids:
        kill(pid)
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


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv[:-1] else ""


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
    rotate_log()
    log("studio start (versi %s)" % (updater.local_version()[:7] or "?"))
    comfy = app = None
    adopted = int(arg("--adopt-comfy") or 0)  # ComfyUI milik supervisor sebelumnya (restart karena update)
    opened = "--no-window" in sys.argv
    next_update = time.time() + 60
    restart_self = False
    misses, need = 0, 1  # saat start langsung; setelahnya 3x berturut-turut mati (15 dtk) baru dinyalakan
    try:
        while True:
            c = cfg()  # baca ulang: pengaturan dari UI langsung berlaku
            alive = comfy_alive(c)
            misses = 0 if alive else misses + 1
            if not alive and misses >= need and (comfy is None or comfy.poll() is not None):
                adopted = misses = 0
                cmd, cwd = comfy_detect.detect(c)
                if cmd:
                    log("start comfy: " + cmd)
                    comfy = subprocess.Popen(cmd, cwd=cwd, shell=True, creationflags=NOWIN,
                                             stdout=open(LOG, "a"), stderr=subprocess.STDOUT)
                else:
                    log("ComfyUI tidak ditemukan; isi comfy_cmd di studio_config.json")
            need = 3
            if app is None or app.poll() is not None:
                log("start app.py")
                exe = sys.executable.replace("pythonw", "python") if os.name == "nt" else sys.executable
                app = subprocess.Popen([exe, "app.py"], creationflags=NOWIN,
                                       stdout=open(LOG, "a"), stderr=subprocess.STDOUT)
            comfy_pid = comfy.pid if comfy and comfy.poll() is None else adopted
            with open(PIDS, "w") as f:
                f.write(" ".join(str(p) for p in (comfy_pid, app.pid) if p) + " %d" % os.getpid())
            if not opened and c["open_window"] and "--background" not in sys.argv:
                time.sleep(1.5)
                open_window(c["app_port"])
                opened = True
            if c.get("auto_update", True) and time.time() >= next_update:
                next_update = time.time() + 600  # dicoba lagi 10 menit bila sibuk / gagal
                if not app_busy(c["app_port"]):
                    try:
                        sha, changed = updater.check_and_apply(log)
                    except Exception as e:
                        sha, changed = None, []
                        log("update gagal: %s" % e)
                    if sha is not None or updater.latest():
                        next_update = time.time() + 3600 * float(c.get("update_check_hours", 3))
                    if changed:
                        if SELF_FILES & set(changed):
                            restart_self = True
                            break
                        log("restart app.py setelah update")
                        app.terminate()
                        app.wait(10)
            time.sleep(5)
    finally:
        if restart_self:  # supervisor baru meneruskan ComfyUI yang sedang jalan
            if app and app.poll() is None:
                app.terminate()
                app.wait(10)
            lock.close()
            exe = sys.executable
            keep = comfy.pid if comfy and comfy.poll() is None else adopted
            log("restart supervisor setelah update")
            subprocess.Popen([exe, os.path.join(BASE, "studio.pyw"), "--no-window", "--adopt-comfy", str(keep or 0)],
                             creationflags=NOWIN)
        else:
            for p in (comfy, app):
                if p and p.poll() is None:
                    p.terminate()


if __name__ == "__main__":
    main()
