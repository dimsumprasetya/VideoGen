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
CLOG = os.path.join(BASE, "comfy.log")  # output ComfyUI sendiri, supaya error-nya bisa ditampilkan di UI
STATE = os.path.join(BASE, "comfy.state.json")  # dibaca app.py: menyala / berhenti / tidak ditemukan
RETRY = os.path.join(BASE, "comfy.retry")  # dibuat app.py: tombol "Nyalakan ulang ComfyUI"
PIDS = os.path.join(BASE, "studio.pids")
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 127.0.0.1: jangan lewat proxy Windows
SELF_FILES = {"studio.pyw", "updater.py", "comfy_detect.py"}  # berubah -> supervisor ikut restart


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def rotate_log(path=LOG):
    try:
        if os.path.getsize(path) > 5 * 1024 * 1024:  # jangan sampai membengkak
            os.replace(path, path + ".old")
    except OSError:
        pass


def write_state(**kw):
    kw["t"] = time.time()
    try:
        with open(STATE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(kw, f)
        os.replace(STATE + ".tmp", STATE)
    except OSError:
        pass


def pid_alive(pid):
    """Proses masih jalan? (Windows: os.kill akan MEMATIKAN proses, jadi pakai OpenProcess.)"""
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


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
        return bool(json.loads(LOCAL.open(req, timeout=5).read().decode()).get("busy"))
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
    since, code, exits, pause_until, state, missing = (time.time() if adopted else 0.0), None, [], 0.0, "", False
    try:
        while True:
          try:
            c = cfg()  # baca ulang: pengaturan dari UI langsung berlaku
            alive = comfy_alive(c)
            misses = 0 if alive else misses + 1
            if comfy is not None and comfy.poll() is not None:  # ComfyUI milik supervisor berhenti
                code, comfy = comfy.returncode, None
                if not alive:  # bukan karena port sudah dipakai ComfyUI lain
                    log("ComfyUI berhenti (kode %s); lihat comfy.log" % code)
                    exits = [t for t in exits if time.time() - t < 600] + [time.time()]
                    if len(exits) >= 3:  # crash berulang: jangan dinyalakan terus-menerus
                        pause_until, exits = time.time() + 300, []
                        log("ComfyUI berhenti 3x dalam 10 menit; dicoba lagi 5 menit lagi")
            if adopted and not pid_alive(adopted):
                adopted = 0
            if os.path.exists(RETRY):  # tombol di UI
                try:
                    os.remove(RETRY)
                except OSError:
                    pass
                pause_until, exits, misses = 0.0, [], max(misses, 3)
                own = comfy.pid if comfy is not None else adopted
                if own:  # ComfyUI milik supervisor macet (port tak kunjung terbuka / tidak menjawab): matikan dulu
                    kill(own)
                    for _ in range(10):  # tunggu port dilepas, lalu langsung dinyalakan lagi
                        if not comfy_alive(c):
                            break
                        time.sleep(0.5)
                    comfy, adopted, alive = None, 0, comfy_alive(c)
                log("nyalakan ulang ComfyUI diminta dari UI")
            if pause_until and time.time() >= pause_until:
                pause_until = 0.0
            if not alive and misses >= need and comfy is None and not adopted and not pause_until:
                misses = 0
                cmd, cwd = comfy_detect.detect(c)
                if cmd:
                    log("start comfy: " + cmd)
                    rotate_log(CLOG)
                    with open(CLOG, "a", encoding="utf-8") as f:
                        f.write("\n%s === start: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), cmd))
                    comfy = subprocess.Popen(cmd, cwd=cwd, shell=True, creationflags=NOWIN,
                                             stdout=open(CLOG, "a"), stderr=subprocess.STDOUT)
                    since, code = time.time(), None
                elif not missing:
                    log("ComfyUI tidak ditemukan; isi lokasinya di Pengaturan (studio_config.json: comfy_cmd)")
                missing = not cmd
            if alive:
                missing = False
            new = ("running" if alive else "starting" if comfy is not None or adopted else "crashloop" if pause_until
                   else "not_found" if missing else "exited" if code is not None else "waiting")
            state = new
            write_state(state=state, since=since, code=code, retry_at=pause_until, own=bool(comfy or adopted))
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
          except Exception as e:  # satu putaran gagal (mis. file terkunci) tidak boleh mematikan ComfyUI & app
              log("supervisor: %r" % e)
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
