#!/usr/bin/env python3
"""Seedance Shorts Studio: web UI lokal -> ComfyUI -> node API Seedance (Text-to-Video).
Hanya pustaka standar Python."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python_embeded tidak otomatis memuat folder script
import comfy_detect
import llm
import json, os, random, re, shutil, subprocess, sys, threading, time, uuid
import urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs")
WF = os.path.join(BASE, "workflows")
PROJ = os.path.join(BASE, "projects")  # breakdown pra-produksi: projects/<nama>.json
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
MIME = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".png": "image/png",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
SHORT_EDGE = {"480p": 480, "720p": 768, "1080p": 1088}

DEFAULT_CFG = {"app_port": 7860, "comfy_ports": [8188, 8000], "poll_seconds": 3,
               "job_timeout_seconds": 1500, "ollama_url": "http://127.0.0.1:11434", "llm_model": "",
               "llm_keep_alive": "2m"}

MODELS = [
    {"id": "seedance-1-0-pro-fast-251015", "label": "Seedance 1.0 Pro Fast", "min_dur": 3, "audio": False},
    {"id": "seedance-1-5-pro-251215", "label": "Seedance 1.5 Pro (audio)", "min_dur": 4, "audio": True},
    {"id": "seedance-1-0-pro-250528", "label": "Seedance 1.0 Pro", "min_dur": 3, "audio": False},
    {"id": "seedance-1-0-lite-t2v-250428", "label": "Seedance 1.0 Lite", "min_dur": 3, "audio": False},
]
ASPECTS = ["9:16", "16:9", "1:1", "3:4", "4:3", "21:9"]
RESOLUTIONS = ["480p", "720p", "1080p"]

JOBS = {}          # id -> dict
LOCK = threading.Lock()


def save_cfg(**kw):
    path = os.path.join(BASE, "studio_config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cur = json.load(f)
    except (OSError, ValueError):
        cur = {}
    cur.update(kw)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
    CFG.update(kw)


def load_cfg():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(os.path.join(BASE, "studio_config.json"), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


CFG = load_cfg()


# ---------------------------------------------------------------- ComfyUI
def http_json(url, data=None, timeout=15):
    req = urllib.request.Request(url, method="POST" if data is not None else "GET")
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


_EXTRA = {"t": 0.0, "ports": []}


def _alive(port):
    u = "http://127.0.0.1:%d" % port
    try:
        http_json(u + "/system_stats", timeout=2)
        return u
    except Exception:
        return None


def comfy_url():
    """URL ComfyUI yang hidup, atau None. Cadangan: cari port dari proses ComfyUI yang sedang jalan
    (mis. dinyalakan aplikasi lain)."""
    env = os.environ.get("COMFYUI_URL", "").rstrip("/")  # sama seperti backend Luminar
    if env:
        try:
            http_json(env + "/system_stats", timeout=2)
            return env
        except Exception:
            pass
    for p in CFG["comfy_ports"]:
        u = _alive(p)
        if u:
            return u
    if time.time() - _EXTRA["t"] > 15:
        _EXTRA["t"] = time.time()
        _EXTRA["ports"] = [r["port"] for r in comfy_detect.running_comfy()]
    for p in _EXTRA["ports"]:
        u = _alive(p)
        if u:
            return u
    return None


KEY_FILE = os.path.join(BASE, "api_key.txt")
NODE = "ByteDanceTextToVideoNode"
_SPEC = {"t": 0.0, "base": "", "spec": None}


def api_key():
    k = os.environ.get("COMFY_API_KEY", "").strip()
    if not k:
        try:
            with open(KEY_FILE, encoding="utf-8") as f:
                k = f.read().strip()
        except OSError:
            pass
    return k


def _combo(spec):
    if isinstance(spec, list) and spec:
        if isinstance(spec[0], list):
            return spec[0]
        if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
            return spec[1].get("options")
    return None


def node_spec(base):
    """Input node Seedance menurut ComfyUI yang terpasang: {"names": set, "combos": {nama: [opsi]}} atau None."""
    if not base:
        return None
    if _SPEC["base"] == base and _SPEC["spec"] and time.time() - _SPEC["t"] < 300:
        return _SPEC["spec"]
    try:
        info = http_json(base + "/object_info/" + NODE, timeout=10).get(NODE)
    except Exception:
        info = None
    if not info:
        return None
    names, combos = set(), {}
    for group in ("required", "optional"):
        for name, spec in (info.get("input", {}).get(group) or {}).items():
            names.add(name)
            opts = _combo(spec)
            if opts:
                combos[name] = opts
    spec = {"names": names, "combos": combos}
    _SPEC.update(t=time.time(), base=base, spec=spec)
    return spec


def model_list(spec):
    if not spec or not spec["combos"].get("model"):
        return MODELS
    known = {m["id"]: m for m in MODELS}
    out = []
    for mid in spec["combos"]["model"]:
        new = "1-5" in mid or "1.5" in mid
        out.append(known.get(mid) or {"id": mid, "label": mid, "min_dur": 4 if new else 3, "audio": new})
    return out


def build_graph(p, spec=None):
    """Workflow bawaan Text-to-Video Seedance (format API)."""
    inputs = {
        "model": p["model"], "prompt": p["prompt"], "resolution": p["resolution"],
        "aspect_ratio": p["aspect"], "duration": p["duration"], "seed": p["seed"],
        "camera_fixed": bool(p.get("camera_fixed")), "watermark": False,
    }
    if p.get("audio") and next((m for m in MODELS if m["id"] == p["model"]), {}).get("audio"):
        inputs["generate_audio"] = True
    if spec:  # kirim hanya input yang memang dimiliki node di ComfyUI ini
        models = spec["combos"].get("model")
        if models and p["model"] not in models:
            raise RuntimeError("Model %s tidak ada di ComfyUI ini. Pilihan: %s" % (p["model"], ", ".join(models)))
        inputs = {k: v for k, v in inputs.items() if k in spec["names"]}
    return {
        "1": {"class_type": "ByteDanceTextToVideoNode", "inputs": inputs},
        "2": {"class_type": "SaveVideo", "inputs": {
            "video": ["1", 0], "filename_prefix": "video/seedance",
            "format": "auto", "codec": "auto"}},
    }


def wf_meta(name):
    """Kunci "_studio" opsional di workflow custom: label, note, max_short, fps, frame_step, frame_offset, timeout."""
    try:
        with open(os.path.join(WF, os.path.basename(name)), encoding="utf-8") as f:
            m = json.load(f).get("_studio")
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def size_for(aspect, resolution, max_short=None):
    """Lebar/tinggi kelipatan 32 dari aspek ("9:16") dan resolusi ("720p")."""
    short = SHORT_EDGE.get(resolution, 768)
    if max_short:
        short = min(short, int(max_short))
    try:
        a, b = (float(x) for x in aspect.split(":"))
    except ValueError:
        a, b = 9.0, 16.0
    long_ = int(short * max(a, b) / min(a, b)) // 32 * 32  # bulatkan ke bawah supaya tidak melebihi batas model
    short = short // 32 * 32
    return (short, long_) if a <= b else (long_, short)


def frames_for(duration, meta):
    """Jumlah frame untuk durasi; dibulatkan naik ke grid model (mis. MiniMax H3: 17k+5 @24fps)."""
    fps, step, off = int(meta.get("fps", 24)), int(meta.get("frame_step", 1)), int(meta.get("frame_offset", 0))
    n = max(off or 1, round(duration * fps))
    return n + (off - n % step) % step


def custom_graph(name, p):
    path = os.path.join(WF, os.path.basename(name))
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta = wf_meta(name)
    w, h = size_for(p["aspect"], p["resolution"], meta.get("max_short"))
    subs = {"{{PROMPT}}": p["prompt"], "{{ASPECT}}": p["aspect"], "{{RESOLUTION}}": p["resolution"]}
    for k, v in subs.items():
        text = text.replace('"%s"' % k, json.dumps(v))
        text = text.replace(k, json.dumps(v)[1:-1])
    nums = {"SEED": p["seed"], "DURATION": p["duration"], "WIDTH": w, "HEIGHT": h,
            "FRAMES": frames_for(p["duration"], meta)}
    for k, v in nums.items():
        text = text.replace('"{{%s}}"' % k, str(v))
    graph = json.loads(text)
    graph.pop("_studio", None)
    return graph


# ---------------------------------------------------------------- model lokal (cek & unduh)
DL = {"active": False, "file": "", "done": 0, "total": 0, "error": "", "finished": []}


def model_status(base, meta):
    """Daftar model workflow (dari _studio.models) + apakah sudah ada di ComfyUI. None bila tidak bisa dicek."""
    want = meta.get("models") or []
    if not want or not base:
        return None
    have = {}
    out = []
    for m in want:
        f = m["folder"]
        if f not in have:
            try:
                have[f] = {os.path.basename(x.replace("\\", "/")) for x in http_json(base + "/models/" + f, timeout=10)}
            except Exception:
                return None
        out.append(dict(m, present=m["file"] in have[f]))
    return out


def model_dir(base, folder):
    """Folder tujuan unduhan: path pertama yang dipakai ComfyUI, cadangan <comfy_cwd>/ComfyUI/models/<folder>."""
    try:
        paths = http_json(base + "/internal/folder_paths", timeout=10).get(folder)
        if paths:
            return paths[0] if isinstance(paths[0], str) else paths[0][0]
    except Exception:
        pass
    cwd = CFG.get("comfy_cwd") or ""
    for root in (os.path.join(cwd, "ComfyUI", "models"), os.path.join(cwd, "models")):
        if cwd and os.path.isdir(root):
            return os.path.join(root, folder)
    raise RuntimeError("Folder models ComfyUI tidak ditemukan. Unduh manual (lihat workflows/README.md).")


def download_models(base, models):
    DL.update(active=True, error="", finished=[])
    try:
        for m in models:
            d = model_dir(base, m["folder"])
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, m["file"])
            if os.path.exists(dst):
                continue
            part = dst + ".part"
            have = os.path.getsize(part) if os.path.exists(part) else 0
            req = urllib.request.Request(m["url"], headers={"User-Agent": "SeedanceStudio"})
            if have:
                req.add_header("Range", "bytes=%d-" % have)  # lanjutkan unduhan yang terputus
            with urllib.request.urlopen(req, timeout=60) as r:
                if have and r.status != 206:
                    have = 0
                total = have + int(r.headers.get("Content-Length") or 0)
                DL.update(file=m["file"], done=have, total=total)
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        DL["done"] += len(chunk)
            os.replace(part, dst)
            DL["finished"].append(m["file"])
    except Exception as e:
        DL["error"] = "Unduh %s gagal: %s (klik Unduh lagi untuk melanjutkan)" % (DL["file"], e)
    finally:
        DL.update(active=False, file="")


def find_videos(outputs):
    """File hasil: video lebih dulu, gambar bila workflow hanya menghasilkan gambar."""
    vids, imgs = [], []
    for node in outputs.values():
        for items in node.values():
            if isinstance(items, list):
                for it in items:
                    fn = str(it.get("filename", "")).lower() if isinstance(it, dict) else ""
                    if fn.endswith(VIDEO_EXT):
                        vids.append(it)
                    elif fn.endswith(IMAGE_EXT) and it.get("type", "output") == "output":
                        imgs.append(it)
    return vids or imgs


def run_job(job):
    try:
        base = comfy_url()
        if not base:
            raise RuntimeError("ComfyUI belum menyala. Tunggu sebentar atau cek studio.log.")
        p = job["params"]
        if p.get("workflow"):
            missing = [m["file"] for m in (model_status(base, wf_meta(p["workflow"])) or []) if not m["present"]]
            if missing:
                raise RuntimeError("Model belum ada di ComfyUI: %s -> Klik 'Unduh model yang kurang'." % ", ".join(missing))
        graph = custom_graph(p["workflow"], p) if p.get("workflow") else build_graph(p, node_spec(base))
        job["status"] = "queued"
        try:
            body = {"prompt": graph, "client_id": job["id"]}
            if api_key():  # node API berbayar butuh API key akun Comfy bila dipanggil tanpa UI ComfyUI
                body["extra_data"] = {"api_key_comfy_org": api_key()}
            res = http_json(base + "/prompt", body, timeout=30)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                j = json.loads(body)
                msg = j.get("error", {}).get("message", body)
                for nid, ne in (j.get("node_errors") or {}).items():
                    for er in ne.get("errors", []):
                        msg += " | node %s: %s %s" % (nid, er.get("message"), er.get("extra_info", ""))
            except ValueError:
                msg = body
            if "does not exist" in msg or "value_not_in_list" in body or "not in list" in msg:
                msg += " -> Node/model belum terpasang. Update ComfyUI dan unduh file model ke folder models (lihat catatan workflow)."
            raise RuntimeError("ComfyUI menolak workflow: " + msg[:800])
        pid = res["prompt_id"]
        job["status"] = "running"
        timeout = wf_meta(p["workflow"]).get("timeout") if p.get("workflow") else None
        deadline = time.time() + max(CFG["job_timeout_seconds"], int(timeout or 0))
        while time.time() < deadline:
            time.sleep(CFG["poll_seconds"])
            h = http_json(base + "/history/" + pid, timeout=15).get(pid)
            if not h:
                continue
            st = h.get("status", {})
            if st.get("status_str") == "error":
                err = ""
                for m in st.get("messages", []):
                    if m and m[0] == "execution_error":
                        err = m[1].get("exception_message", "")
                raise RuntimeError("Gagal di ComfyUI: " + (err or "unknown error")[:600])
            vids = find_videos(h.get("outputs", {}))
            if vids:
                v = vids[0]
                url = "%s/view?filename=%s&subfolder=%s&type=%s" % (
                    base, quote(v["filename"]), quote(v.get("subfolder", "")), quote(v.get("type", "output")))
                name = "%s_%s%s" % (time.strftime("%Y%m%d-%H%M%S"), job["id"][:6],
                                    os.path.splitext(v["filename"])[1])
                os.makedirs(OUT, exist_ok=True)
                with urllib.request.urlopen(url, timeout=120) as r, open(os.path.join(OUT, name), "wb") as f:
                    shutil.copyfileobj(r, f)
                job["file"] = name
                job["status"] = "done"
                save_meta(job)
                return
        try:  # batalkan job macet supaya antrian ComfyUI tidak tersumbat
            http_json(base + "/queue", {"delete": [pid]}, timeout=10)
            http_json(base + "/interrupt", {}, timeout=10)
        except Exception:
            pass
        raise RuntimeError("Timeout menunggu hasil dari ComfyUI (job dibatalkan).")
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if any(w in low for w in ("unauthorized", "login", "api key", "401", "authenticat")):
            msg += " -> Isi API key akun Comfy di bagian Pengaturan (buat di platform.comfy.org)."
        elif "credit" in low or "balance" in low or "402" in low:
            msg += " -> Kredit akun Comfy habis/kurang."
        job["status"] = "error"
        job["error"] = msg


def save_meta(job):
    meta = {k: job[k] for k in ("id", "params", "file", "created")}
    with open(os.path.join(OUT, job["file"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def load_history():
    if not os.path.isdir(OUT):
        return
    for fn in sorted(os.listdir(OUT)):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(OUT, fn), encoding="utf-8") as f:
                    m = json.load(f)
                if os.path.exists(os.path.join(OUT, m["file"])):
                    m.update(status="done", error="")
                    JOBS[m["id"]] = m
            except (OSError, ValueError, KeyError):
                pass


def clean_params(d):
    scene = str(d.get("prompt", "")).strip()
    if not scene:
        raise ValueError("Prompt kosong.")
    style = str(d.get("style", "")).strip()  # gaya/karakter tetap, ditaruh di depan prompt scene
    prompt = style + "\n" + scene if style else scene
    model = d.get("model") or MODELS[0]["id"]
    m = next((x for x in MODELS if x["id"] == model), None)
    dur = max(m["min_dur"] if m else 3, min(15, int(d.get("duration", 5))))
    seed = int(d.get("seed", -1))
    if seed < 0:
        seed = random.randint(0, 2**31 - 1)
    return {
        "prompt": prompt, "scene": scene, "model": model, "duration": dur, "seed": seed,
        "aspect": str(d.get("aspect") or "9:16")[:20],          # opsi sebenarnya divalidasi ComfyUI
        "resolution": str(d.get("resolution") or "720p")[:20],
        "audio": bool(d.get("audio")), "camera_fixed": bool(d.get("camera_fixed")),
        "workflow": os.path.basename(d["workflow"]) if d.get("workflow") else "",
    }


def proj_path(name):
    name = re.sub(r"[^\w\- ]", "", str(name or "")).strip()[:60]
    if not name:
        raise ValueError("Nama proyek kosong.")
    return os.path.join(PROJ, name + ".json")


def llm_base():
    return os.environ.get("OLLAMA_HOST_URL", "").rstrip("/") or CFG["ollama_url"].rstrip("/")


def llm_run(d):
    base = llm_base()
    model = llm.pick_model(base, CFG.get("llm_model", ""))
    if not model:
        raise RuntimeError("Belum ada model di Ollama. Klik 'Unduh %s' dulu." % llm.RECOMMENDED)
    with LOCK:
        busy = any(j["status"] in ("queued", "running") for j in JOBS.values())
    cb = comfy_url()
    if cb and not busy:  # VRAM 8 GB: kosongkan model ComfyUI dulu supaya LLM tidak berebut VRAM
        try:
            http_json(cb + "/free", {"unload_models": True, "free_memory": True}, timeout=5)
        except Exception:
            pass
    task = {"ideas": llm.ideas, "storyline": llm.storyline, "script": llm.script}.get(d.get("task"))
    if not task:
        raise ValueError("Tugas LLM tidak dikenal.")
    res = task(base, model, d)
    res["_model"] = model
    return res


def merge(files):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg tidak ditemukan di PATH.")
    paths = [os.path.join(OUT, os.path.basename(f)) for f in files]
    if any(not p.lower().endswith(VIDEO_EXT) for p in paths):
        raise RuntimeError("Hanya klip video yang bisa digabung.")
    if len(paths) < 2 or not all(os.path.exists(p) for p in paths):
        raise RuntimeError("Pilih minimal 2 klip yang ada.")
    name = "merged_%s.mp4" % time.strftime("%Y%m%d-%H%M%S")
    lst = os.path.join(OUT, ".concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in paths:
            f.write("file '%s'\n" % p.replace("'", "'\\''"))
    base = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264",
            "-pix_fmt", "yuv420p"]
    dst = os.path.join(OUT, name)
    r = subprocess.run(base + ["-c:a", "aac", dst], capture_output=True)
    if r.returncode:
        r = subprocess.run(base + ["-an", dst], capture_output=True)  # klip tanpa audio
    os.remove(lst)
    if r.returncode:
        raise RuntimeError("ffmpeg gagal: " + r.stderr.decode(errors="replace")[-300:])
    return name


# ---------------------------------------------------------------- HTTP
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            b = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif u.path == "/api/config":
            names = sorted(f for f in os.listdir(WF) if f.endswith(".json")) if os.path.isdir(WF) else []
            wfs = [{"file": f, "label": wf_meta(f).get("label") or f, "note": wf_meta(f).get("note", "")}
                   for f in names]
            spec = node_spec(comfy_url())
            cb = spec["combos"] if spec else {}
            self.send_json({"models": model_list(spec), "aspects": cb.get("aspect_ratio") or ASPECTS,
                            "resolutions": cb.get("resolution") or RESOLUTIONS, "live": bool(spec),
                            "workflows": wfs})
        elif u.path == "/api/status":
            log = ""
            try:
                with open(os.path.join(BASE, "studio.log"), encoding="utf-8", errors="replace") as f:
                    log = "\n".join(f.read().splitlines()[-4:])
            except OSError:
                pass
            self.send_json({"comfy": bool(comfy_url()), "ffmpeg": bool(shutil.which("ffmpeg")), "log": log,
                            "has_key": bool(api_key())})
        elif u.path == "/api/comfy/detect":
            cmd, cwd = comfy_detect.detect(CFG)
            self.send_json({"found": bool(cmd), "cmd": cmd or "", "cwd": cwd or ""})
        elif u.path == "/api/models":
            wf = os.path.basename(parse_qs(u.query).get("workflow", [""])[0])
            ms = model_status(comfy_url(), wf_meta(wf)) if wf else None
            self.send_json({"models": ms, "dl": DL})
        elif u.path == "/api/projects":
            names = sorted(f[:-5] for f in os.listdir(PROJ) if f.endswith(".json")) if os.path.isdir(PROJ) else []
            self.send_json(names)
        elif u.path == "/api/project":
            try:
                with open(proj_path(parse_qs(u.query).get("name", [""])[0]), encoding="utf-8") as f:
                    self.send_json(json.load(f))
            except (OSError, ValueError):
                self.send_json({})
        elif u.path == "/api/llm/status":
            st = llm.status(llm_base())
            st.update(model=llm.pick_model(llm_base(), CFG.get("llm_model", "")) if st["ok"] else "",
                      recommended=llm.RECOMMENDED, alternatives=llm.ALTERNATIVES, pull=llm.PULL, url=llm_base())
            self.send_json(st)
        elif u.path == "/api/jobs":
            with LOCK:
                jobs = sorted(JOBS.values(), key=lambda j: j["created"], reverse=True)
            self.send_json(jobs)
        elif u.path.startswith("/outputs/"):
            self.serve_file(os.path.basename(u.path))
        else:
            self.send_json({"error": "not found"}, 404)

    def serve_file(self, name):
        path = os.path.join(OUT, name)
        if not os.path.isfile(path):
            return self.send_json({"error": "not found"}, 404)
        size = os.path.getsize(path)
        start, end, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else end
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", MIME.get(os.path.splitext(name)[1].lower(), "application/octet-stream"))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except OSError:
                    break
                left -= len(chunk)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/generate":
                p = clean_params(d)
                job = {"id": uuid.uuid4().hex, "params": p, "status": "queued", "file": "",
                       "error": "", "created": time.time()}
                with LOCK:
                    JOBS[job["id"]] = job
                threading.Thread(target=run_job, args=(job,), daemon=True).start()
                self.send_json(job)
            elif self.path == "/api/comfy/save":
                m = re.match(r"^(?:https?://)?(?:127\.0\.0\.1|localhost)?:?(\d{2,5})/?$", (d.get("path") or "").strip())
                if m:  # user memasukkan port / URL ComfyUI yang sudah jalan
                    port = int(m.group(1))
                    if not _alive(port):
                        raise RuntimeError("Tidak ada ComfyUI di port %d." % port)
                    save_cfg(comfy_ports=[port] + [x for x in CFG["comfy_ports"] if x != port])
                    return self.send_json({"cmd": "port %d" % port, "cwd": ""})
                r = comfy_detect.resolve(d.get("path", "")) if d.get("path") else None
                if not r:
                    cmd, cwd = comfy_detect.detect({})
                    r = (cmd, cwd) if cmd else None
                if not r:
                    raise RuntimeError("ComfyUI tidak ditemukan di lokasi itu. Pilih ComfyUI.exe atau folder yang berisi main.py.")
                save_cfg(comfy_cmd=r[0], comfy_cwd=r[1] or "")
                self.send_json({"cmd": r[0], "cwd": r[1] or ""})
            elif self.path == "/api/models/download":
                base = comfy_url()
                ms = model_status(base, wf_meta(os.path.basename(d.get("workflow", ""))))
                if ms is None:
                    raise RuntimeError("ComfyUI belum menyala, atau workflow ini tidak punya daftar model.")
                todo = [m for m in ms if not m["present"]]
                if todo and not DL["active"]:
                    threading.Thread(target=download_models, args=(base, todo), daemon=True).start()
                self.send_json({"started": bool(todo)})
            elif self.path == "/api/llm/run":
                self.send_json(llm_run(d))
            elif self.path == "/api/llm/pull":
                if not llm.status(llm_base())["ok"]:
                    raise RuntimeError("Ollama belum menyala. Pasang dari ollama.com lalu jalankan.")
                llm.pull(llm_base(), str(d.get("model") or llm.RECOMMENDED))
                self.send_json({"ok": True})
            elif self.path == "/api/llm/model":
                save_cfg(llm_model=str(d.get("model", "")))
                self.send_json({"ok": True})
            elif self.path == "/api/project":
                path = proj_path(d.get("name"))
                os.makedirs(PROJ, exist_ok=True)
                if d.get("delete"):
                    if os.path.exists(path):
                        os.remove(path)
                else:
                    tmp = path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(d.get("data") or {}, f, ensure_ascii=False, indent=1)
                    os.replace(tmp, path)
                self.send_json({"ok": True})
            elif self.path == "/api/apikey":
                k = str(d.get("key", "")).strip()
                if k:
                    with open(KEY_FILE, "w", encoding="utf-8") as f:
                        f.write(k)
                elif os.path.exists(KEY_FILE):
                    os.remove(KEY_FILE)
                self.send_json({"has_key": bool(api_key())})
            elif self.path == "/api/merge":
                name = merge(d.get("files", []))
                job = {"id": uuid.uuid4().hex, "params": {"prompt": "Gabungan %d klip" % len(d["files"])},
                       "status": "done", "file": name, "error": "", "created": time.time()}
                with LOCK:
                    JOBS[job["id"]] = job
                save_meta(job)
                self.send_json({"file": name})
            elif self.path == "/api/delete":
                name = os.path.basename(d.get("file", ""))
                for fn in (name, name + ".json"):
                    try:
                        os.remove(os.path.join(OUT, fn))
                    except OSError:
                        pass
                with LOCK:
                    for k in [k for k, j in JOBS.items() if j.get("file") == name]:
                        del JOBS[k]
                self.send_json({"ok": True})
            else:
                self.send_json({"error": "not found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 400)


HTML = r"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Seedance Studio</title>
<style>
:root{--bg:#0e0f12;--panel:#16181d;--line:#262932;--tx:#e8eaf0;--mut:#8b90a0;--ac:#ff8a3d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px system-ui,sans-serif;height:100vh;display:flex;flex-direction:column}
nav{flex:0 0 40px;display:flex;gap:4px;align-items:center;padding:0 12px;border-bottom:1px solid var(--line);background:var(--panel)}
nav b{margin-right:12px}nav a{padding:6px 14px;border-radius:8px;color:var(--mut);cursor:pointer;text-decoration:none}nav a.on{background:#262932;color:var(--tx)}
#studio{flex:1;min-height:0;display:grid;grid-template-columns:320px 1fr;grid-template-rows:1fr 150px}
aside{grid-row:1/3;background:var(--panel);border-right:1px solid var(--line);padding:16px;overflow:auto}
h1{font-size:15px;margin:0 0 14px;display:flex;justify-content:space-between;align-items:center}
.chip{font-size:11px;padding:2px 8px;border-radius:99px;background:#3a2a1a;color:var(--ac)}.chip.ok{background:#173323;color:#4ade80}
label{display:block;color:var(--mut);font-size:12px;margin:12px 0 4px}
textarea,select,input[type=number]{width:100%;background:#0e0f12;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:8px;font:inherit}
textarea{height:120px;resize:vertical}input[type=range]{width:100%;accent-color:var(--ac)}
.row{display:flex;gap:8px;align-items:center}.row>*{flex:1}.chk{display:flex;gap:6px;align-items:center;color:var(--tx);margin:10px 0 0}
.chk input{width:auto}
button{background:var(--ac);color:#1a0d00;border:0;border-radius:8px;padding:10px;font-weight:600;cursor:pointer;width:100%;margin-top:16px}
button.sec{background:#262932;color:var(--tx);margin-top:6px;padding:8px}button:disabled{opacity:.5}
main{display:flex;align-items:center;justify-content:center;padding:16px;min-height:0}
video{max-width:100%;max-height:100%;border-radius:10px;background:#000}#msg{color:var(--mut);text-align:center;max-width:420px}
footer{border-top:1px solid var(--line);background:var(--panel);display:flex;gap:10px;padding:10px;overflow-x:auto}
.card{flex:0 0 auto;width:120px;border:2px solid var(--line);border-radius:8px;padding:6px;font-size:11px;cursor:pointer;position:relative;display:flex;flex-direction:column;gap:4px}
.card.sel{border-color:var(--ac)}.card .p{overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;color:var(--mut)}
.card .s{font-weight:600}.s.error{color:#f87171}.s.done{color:#4ade80}.card input{position:absolute;top:6px;right:6px}
.card .x{position:absolute;bottom:4px;right:6px;color:var(--mut)}
.pg{flex:1;min-height:0;display:none;grid-template-columns:340px 1fr}
.pg .side{background:var(--panel);border-right:1px solid var(--line);padding:16px;overflow:auto}
.pg .side input,.pg .grid input,.pg .grid select{width:100%;background:#0e0f12;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:7px;font:inherit}
.pg .body{overflow:auto;padding:16px 20px}
.pg h2{font-size:14px;margin:18px 0 10px;display:flex;align-items:center;gap:10px}.pg h2:first-child{margin-top:0}
.pg h2 button{width:auto;margin:0;padding:5px 12px;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
.it{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:6px}
.it .img{aspect-ratio:1;background:#0e0f12;border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--mut);font-size:12px;overflow:hidden;cursor:pointer}
.it .img img{width:100%;height:100%;object-fit:cover}.it textarea{height:70px}
.it .btns{display:flex;gap:6px}.it .btns button{margin:0;padding:7px;font-size:12px}
.it .tags{display:flex;flex-wrap:wrap;gap:4px 10px;font-size:12px}.it .tags label{margin:0;display:flex;gap:4px;align-items:center;color:var(--tx)}
.hint{font-size:12px;color:var(--mut)}
nav .sp{flex:1}nav select{background:#0e0f12;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:5px;font:inherit;max-width:180px}
nav button{width:auto;margin:0;padding:5px 10px;font-size:12px}nav .n{display:inline-block;width:18px;height:18px;border-radius:9px;background:#262932;font-size:11px;text-align:center;line-height:18px;margin-right:6px}
nav a.ok .n{background:#173323;color:#4ade80}
.idea{cursor:pointer}.idea.on{border-color:var(--ac)}.idea b{font-size:14px}.idea p{margin:0;color:var(--mut);font-size:13px}
.sc{display:grid;grid-template-columns:150px 1fr 1fr;gap:8px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:10px}
.sc textarea{height:64px}.sc .c{display:flex;flex-direction:column;gap:6px}.sc label{margin:0}
.sc input{width:100%;background:#0e0f12;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:6px;font:inherit}
.sc .btns{display:flex;gap:4px;flex-wrap:wrap}.sc .btns button{margin:0;padding:5px 8px;font-size:12px;width:auto}
.llm{background:#0e0f12;border:1px solid var(--line);border-radius:8px;padding:8px;font-size:12px;margin-top:12px}
#lb{position:fixed;inset:0;background:#000c;display:none;align-items:center;justify-content:center;z-index:9}#lb img{max-width:92vw;max-height:92vh}
</style></head><body>
<nav><b>Seedance Studio</b>
<a data-tab="idea"><span class="n">1</span>Ide</a><a data-tab="scr"><span class="n">2</span>Script</a><a data-tab="bd"><span class="n">3</span>Breakdown</a>
<a data-tab="prod"><span class="n">4</span>Production</a><a data-tab="edit"><span class="n">5</span>Editing &amp; Sound</a>
<span class="sp"></span><span class="hint" id="bsave" style="margin-right:8px"></span><select id="pj" title="Proyek"></select><button class="sec" id="pjnew">Baru</button><button class="sec" id="pjdel">Hapus</button></nav>
<div id="idea" class="pg"><div class="side">
<label style="margin-top:0">Prompt ide</label><textarea id="d-prompt" style="height:130px" placeholder="Video edukasi anak belajar kata sapaan Jepang bersama bayi panda merah yang lucu"></textarea>
<div class="row"><div><label>Penonton</label><input id="d-audience" placeholder="anak 4-8 tahun"></div><div><label>Genre</label><input id="d-genre" placeholder="edukasi, komedi"></div></div>
<div class="row"><div><label>Tone</label><input id="d-tone" placeholder="ceria, hangat"></div><div><label>Jumlah ide</label><input id="d-count" type="number" min="1" max="8" value="4"></div></div>
<label>Bahasa cerita</label><select id="d-lang"><option>Bahasa Indonesia</option><option>English</option><option>日本語</option></select>
<button id="d-go">Generate ide</button>
<div class="llm" id="llmbox1"></div>
</div><div class="body">
<h2>Ide <span class="hint">Klik ide untuk memilih, lalu kembangkan jadi storyline. Teks bisa diedit.</span></h2><div class="grid" id="d-ideas"></div>
<h2>Storyline <button id="d-story">Kembangkan ide terpilih</button><button class="sec" id="d-next">Lanjut ke Script →</button></h2>
<textarea id="d-storyline" style="height:340px" placeholder="Pilih ide lalu klik 'Kembangkan', atau tulis storyline sendiri."></textarea>
<div class="hint" id="d-msg"></div>
</div></div>
<div id="scr" class="pg"><div class="side">
<label style="margin-top:0">Durasi total video</label><select id="s-total"><option>15</option><option selected>30</option><option>45</option><option>60</option><option>90</option></select>
<label>Maks. durasi per scene (detik)</label><input id="s-max" type="number" min="3" max="15" value="8">
<div class="hint">Sesuaikan dengan model video: Seedance 3-12 dtk, MiniMax H3 sampai ~15 dtk.</div>
<button id="s-go">Generate script dari storyline</button>
<div id="s-sum" style="margin-top:10px;font-weight:600"></div>
<button class="sec" id="s-bd">Kirim scene ke Breakdown (panel storyboard)</button>
<div class="llm" id="llmbox2"></div>
</div><div class="body">
<h2>Scene <button class="sec" id="s-add">+ Scene</button><span class="hint" id="s-msg"></span></h2><div id="s-list"></div>
</div></div>
<div id="studio" class="view">
<aside>
<h1>Generate <span id="st" class="chip">ComfyUI…</span></h1>
<div id="setup" style="display:none;background:#2a1d12;border:1px solid #5a3a1a;border-radius:8px;padding:10px;margin-bottom:8px">
<b>ComfyUI belum tersambung</b><div style="color:var(--mut);font-size:12px;margin:4px 0">Klik cari otomatis, atau tempel lokasi ComfyUI.exe / folder ComfyUI / port (mis. 8000) bila ComfyUI sudah jalan.</div>
<input id="cpath" placeholder="Lokasi ComfyUI.exe atau folder ComfyUI" style="width:100%;background:#0e0f12;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:8px;font:inherit">
<button id="cfind" style="margin-top:8px">Cari &amp; sambungkan</button><div id="cmsg" style="font-size:12px;margin-top:6px;color:var(--mut)"></div><pre id="clog" style="font-size:11px;color:var(--mut);white-space:pre-wrap;margin:6px 0 0"></pre></div>
<label>Workflow</label><select id="wf"><option value="">Seedance cloud (bayar kredit Comfy)</option></select>
<div id="wfnote" style="font-size:12px;color:var(--mut);margin-top:4px"></div>
<div id="mdl" style="display:none;font-size:12px;word-break:break-all;margin-top:6px;background:#0e0f12;border:1px solid var(--line);border-radius:8px;padding:8px"><div id="mlist"></div>
<button class="sec" id="mdown" style="display:none">Unduh model yang kurang</button><div id="mprog" style="color:var(--mut);margin-top:4px"></div></div>
<label>Gaya &amp; karakter (tetap untuk semua scene, opsional)</label><textarea id="style" style="height:70px" placeholder="STYLE: animasi 3D lucu… CHARACTERS: &quot;Kiko&quot;, bayi panda merah… SETTING: …"></textarea>
<label>Scene / prompt</label><textarea id="prompt" placeholder="Seekor kucing oranye berlari di atap kota saat senja, kamera mengikuti, sinematik"></textarea>
<div id="sdw"><label>Model</label><select id="model"></select></div>
<div class="row"><div><label>Aspek</label><select id="aspect"></select></div><div><label>Resolusi</label><select id="res"></select></div></div>
<label>Durasi: <b id="dv">5</b> detik</label><input type="range" id="dur" min="3" max="15" value="5">
<div class="row"><div><label>Seed (-1 = acak)</label><input type="number" id="seed" value="-1"></div></div>
<div class="chk" id="audw"><input type="checkbox" id="aud"><span>Generate audio</span></div>
<div class="chk" id="camw"><input type="checkbox" id="cam"><span>Kamera tetap</span></div>
<button id="go">Generate</button>
<button class="sec" id="merge" disabled>Gabung klip terpilih</button>
<label>API key akun Comfy <span id="kst"></span></label>
<input type="password" id="key" placeholder="comfyui-…  (dari platform.comfy.org)" style="width:100%;background:#0e0f12;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:8px;font:inherit">
<button class="sec" id="ksave">Simpan API key</button>
</aside>
<main><video id="v" controls loop style="display:none"></video><img id="im" style="display:none;max-width:100%;max-height:100%;border-radius:10px"><div id="msg">Tulis prompt lalu klik Generate. Hasil muncul di bawah.</div></main>
<footer id="list"></footer>
</div>
<div id="bd" class="pg">
<div class="side">
<label style="margin-top:0">Script / beats</label><textarea id="bscript" style="height:220px"></textarea>
<button class="sec" id="bbeats">Pecah beats bernomor jadi panel storyboard</button>
<label>Gaya visual (dipakai di gambar karakter & lokasi)</label><textarea id="bstyle" style="height:90px" placeholder="Cute 3D animation, soft plush and clay texture, pastel but vivid colors…"></textarea>
<label>Workflow gambar</label><select id="bwf"></select>
<div class="hint" id="bwfh"></div>
<button id="bstyle2">Isi "Gaya &amp; karakter" di Production dari breakdown</button>
</div>
<div class="body">
<h2>Karakter <button class="sec" data-add="chars">+ Tambah</button></h2><div class="grid" id="g-chars"></div>
<h2>Set / Lokasi <button class="sec" data-add="locs">+ Tambah</button></h2><div class="grid" id="g-locs"></div>
<h2>Storyboard <button class="sec" data-add="panels">+ Panel</button><span class="hint">Sketsa per panel; "Ke Production" mengisi prompt scene + durasi.</span></h2><div class="grid" id="g-panels"></div>
</div>
</div>
<div id="edit" class="pg"><div class="side"><h2 style="margin:0">Editing &amp; Sound</h2>
<p class="hint">Tahap berikutnya: timeline urutan take, potong awal/akhir, transisi, musik/SFX/VO, subtitle, render final 9:16.</p>
<p class="hint">Untuk sekarang: centang klip di tab Production lalu klik "Gabung klip terpilih".</p></div><div class="body"></div></div>
<div id="lb" onclick="this.style.display='none'"><img id="lbi"></div>
<script>
const $=id=>document.getElementById(id);let cfg,sel=new Set(),cur="";
const api=(p,b)=>fetch(p,b?{method:"POST",body:JSON.stringify(b)}:{}).then(r=>r.json());
function mdl(){return cfg.models.find(m=>m.id==$("model").value)}
const store=(k,v)=>{try{if(v===undefined)return localStorage.getItem(k)||"";localStorage.setItem(k,v)}catch(e){return ""}};
function sync(){const m=mdl(),w=$("wf").value,info=(cfg.workflows||[]).find(x=>x.file==w);$("dur").max=w?15:12;$("dur").min=w?1:m.min_dur;
if(+$("dur").value<+$("dur").min)$("dur").value=$("dur").min;if(+$("dur").value>+$("dur").max)$("dur").value=$("dur").max;$("dv").textContent=$("dur").value;
$("sdw").style.display=$("camw").style.display=w?"none":"";$("audw").style.display=!w&&m.audio?"flex":"none";$("wfnote").textContent=info?info.note:"Butuh API key + kredit akun Comfy."}
async function init(){$("style").value=store("style");$("style").oninput=()=>store("style",$("style").value);await fill();
$("model").onchange=$("dur").oninput=sync;$("wf").onchange=()=>{store("wf",$("wf").value);sync();models().catch(()=>{})};poll();setInterval(poll,2000);status();setInterval(status,5000)}
async function fill(){cfg=await api("/api/config");const cur=$("model").value;
$("model").innerHTML=cfg.models.map(m=>`<option value="${m.id}">${m.label}</option>`).join("");
$("aspect").innerHTML=cfg.aspects.map(a=>`<option ${a=="9:16"?"selected":""}>${a}</option>`).join("");
$("res").innerHTML=cfg.resolutions.map(a=>`<option ${a=="720p"?"selected":""}>${a}</option>`).join("");
if(cur&&cfg.models.some(m=>m.id==cur))$("model").value=cur;const wv=$("wf").value||store("wf");$("wf").length=1;
cfg.workflows.forEach(w=>{const o=document.createElement("option");o.value=w.file;o.textContent=w.label;$("wf").appendChild(o)});
if(cfg.workflows.some(w=>w.file==wv))$("wf").value=wv;sync()}
async function models(){const w=$("wf").value;if(!w){$("mdl").style.display="none";return}
const r=await api("/api/models?workflow="+encodeURIComponent(w)),d=r.dl;$("mdl").style.display="block";
if(!r.models){$("mlist").textContent="Status model belum bisa dicek (ComfyUI mati?).";$("mdown").style.display="none"}
else{const miss=r.models.filter(m=>!m.present),gb=miss.reduce((a,m)=>a+(m.gb||0),0);
$("mlist").innerHTML=r.models.map(m=>`<div style="color:${m.present?"#4ade80":"#f87171"}">${m.present?"✓":"✗"} ${m.folder}/${m.file}${m.gb?" ("+m.gb+" GB)":""}</div>`).join("");
$("mdown").style.display=miss.length&&!d.active?"block":"none";$("mdown").textContent=`Unduh model yang kurang (~${gb.toFixed(1)} GB)`}
$("mprog").textContent=d.active?`Mengunduh ${d.file}: ${(d.done/1e9).toFixed(2)} / ${(d.total/1e9).toFixed(2)} GB`:(d.error||"")}
$("mdown").onclick=async()=>{const r=await api("/api/models/download",{workflow:$("wf").value});if(r.error)alert(r.error);models()};
async function status(){models().catch(()=>{});try{const s=await api("/api/status");$("st").textContent=s.comfy?"ComfyUI aktif":"ComfyUI mati";$("st").className="chip"+(s.comfy?" ok":"");$("setup").style.display=s.comfy?"none":"block";$("clog").textContent=s.log||"";$("kst").textContent=s.has_key?"(tersimpan)":"(belum diisi)";if(s.comfy&&!cfg.live)fill();$("merge").dataset.ff=s.ffmpeg?1:""}catch(e){}}
$("cfind").onclick=async()=>{$("cmsg").textContent="Mencari…";const r=await api("/api/comfy/save",{path:$("cpath").value});
$("cmsg").textContent=r.error?r.error:"Tersimpan. Menyalakan ComfyUI, tunggu sebentar…"};
$("ksave").onclick=async()=>{const r=await api("/api/apikey",{key:$("key").value});$("key").value="";$("kst").textContent=r.has_key?"(tersimpan)":"(belum diisi)"};
$("go").onclick=async()=>{const r=await api("/api/generate",{prompt:$("prompt").value,style:$("style").value,model:$("model").value,aspect:$("aspect").value,resolution:$("res").value,duration:+$("dur").value,seed:+$("seed").value,audio:$("aud").checked,camera_fixed:$("cam").checked,workflow:$("wf").value});if(r.error)alert(r.error);else poll()};
const isImg=f=>/\.(png|jpe?g|webp)$/i.test(f);
function play(f){cur=f;$("msg").style.display="none";if(isImg(f)){$("v").pause();$("v").style.display="none";$("im").src="/outputs/"+f;$("im").style.display="block"}
else{$("im").style.display="none";$("v").src="/outputs/"+f;$("v").style.display="block";$("v").play().catch(()=>{})}render(last)}
let last=[];
function render(jobs){last=jobs;$("list").innerHTML=jobs.map(j=>{const d=j.status=="done";
return `<div class="card ${j.file&&j.file==cur?"sel":""}" onclick="${d?`play('${j.file}')`:`alert(${JSON.stringify(j.error||"Sedang diproses…").replace(/"/g,"&quot;")})`}">
${d&&!isImg(j.file)?`<input type="checkbox" ${sel.has(j.file)?"checked":""} onclick="event.stopPropagation();tog('${j.file}')">`:""}
<span class="s ${j.status}">${{queued:"Antre…",running:"Memproses…",done:"Selesai",error:"Gagal"}[j.status]}</span>
<span class="p">${(j.params.scene||j.params.prompt).replace(/</g,"&lt;")}</span>
${d?`<span class="x" onclick="event.stopPropagation();del('${j.file}')">hapus</span>`:""}</div>`}).join("");
$("merge").disabled=sel.size<2}
function tog(f){sel.has(f)?sel.delete(f):sel.add(f);$("merge").disabled=sel.size<2}
async function del(f){if(!confirm("Hapus klip ini?"))return;await api("/api/delete",{file:f});sel.delete(f);poll()}
async function poll(){const j=await api("/api/jobs");render(j);bdJobs(j)}
$("merge").onclick=async()=>{$("merge").disabled=true;const order=last.filter(j=>sel.has(j.file)).reverse().map(j=>j.file);const r=await api("/api/merge",{files:order});if(r.error)alert(r.error);else{sel.clear();await poll();play(r.file)}};
/* ---------------- Breakdown */
const SHOTS=["Wide","Medium","Close-up","Extreme close-up","Over-the-shoulder","POV","Top-down"];
const CAMS=["Static","Pan","Tilt","Push-in","Pull-out","Tracking","Handheld","Orbit"];
const TPL={chars:(it,P)=>`Character design sheet of ${it.name||"the character"}: ${it.desc}. ${P.style?"Style: "+P.style+". ":""}Full-body and close-up portrait, neutral studio background, clear consistent facial features and wardrobe, front and three-quarter views, cinematic lighting, high detail reference sheet`,
locs:(it,P)=>`Establishing shot of ${it.name||"the location"}: ${it.desc}. ${P.style?"Style: "+P.style+". ":""}Wide cinematic environment, consistent architecture and set dressing, atmospheric lighting and time of day, no characters, concept art quality, high detail`,
panels:(it,P)=>`Hand-drawn storyboard sketch panel, rough black-and-white line-sketch style (not a polished poster). ${it.shot} shot, camera ${it.cam}. ${it.desc}. ${scene(it,P,true)} Show composition, character position and camera-move arrows, one caption line: "${(it.desc||"").slice(0,60).replace(/"/g,"'")}"`};
const BLANK=()=>({dev:{prompt:"",audience:"",genre:"",tone:"",lang:"Bahasa Indonesia",count:4,ideas:[],chosen:-1},story:"",target:30,maxScene:8,scenes:[],script:"TITLE: [Judul]\n\nLOGLINE: Satu kalimat ringkasan.\n\nSCRIPT / BEATS:\n1. Opening — apa yang terlihat.\n2. Rising action — apa yang terjadi.\n3. Turn — momen kunci.\n4. Resolution — gambar penutup.",style:"",chars:[],locs:[],panels:[]});
let P=BLANK(),PN="",bdT=0;
const esc=s=>String(s??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
const uid=()=>Math.random().toString(36).slice(2,9);
function scene(it,P,short){const loc=P.locs.find(l=>l.id==it.loc),cs=P.chars.filter(c=>(it.chars||[]).includes(c.id));
return (loc?`Location: ${loc.name}${short?"":" — "+loc.desc}. `:"")+(cs.length?`Characters: ${cs.map(c=>c.name+(short?"":" ("+c.desc+")")).join(", ")}.`:"")}
const VIEWS={idea:"idea",scr:"scr",bd:"bd",prod:"studio",edit:"edit"};
function tab(t){if(!VIEWS[t])t=t=="studio"?"prod":"idea";store("tab",t);for(const k in VIEWS)$(VIEWS[k]).style.display=k==t?"grid":"none";
document.querySelectorAll("nav [data-tab]").forEach(a=>a.classList.toggle("on",a.dataset.tab==t));if(t=="bd")bdImgWf();if(t=="idea"||t=="scr")llmStatus()}
document.querySelectorAll("nav [data-tab]").forEach(a=>a.onclick=()=>tab(a.dataset.tab));
function bdImgWf(){const keep=$("bwf").value||store("bwf");$("bwf").innerHTML=(cfg.workflows||[]).map(w=>`<option value="${esc(w.file)}">${esc(w.label)}</option>`).join("");
const z=(cfg.workflows||[]).find(w=>/image|gambar/i.test(w.file));if((cfg.workflows||[]).some(w=>w.file==keep))$("bwf").value=keep;else if(z)$("bwf").value=z.file;
$("bwfh").textContent=(cfg.workflows||[]).length?"Model lokal; cek/unduh model lewat dropdown Workflow di tab Studio.":"Belum ada workflow gambar di folder workflows."}
$("bwf").onchange=()=>store("bwf",$("bwf").value);
async function bdList(sel){const ns=await api("/api/projects");if(!ns.length)ns.push("Proyek 1");
$("pj").innerHTML=ns.map(n=>`<option>${esc(n)}</option>`).join("");$("pj").value=ns.includes(sel)?sel:ns[0];await bdLoad($("pj").value)}
async function bdLoad(n){PN=n;store("pj",n);const d=await api("/api/project?name="+encodeURIComponent(n));P=Object.assign(BLANK(),d||{});
$("bscript").value=P.script;$("bstyle").value=P.style;bdRender();devLoad();scrRender();navDone()}
function bdSave(){navDone();clearTimeout(bdT);$("bsave").textContent="Menyimpan…";bdT=setTimeout(async()=>{const r=await api("/api/project",{name:PN,data:P});$("bsave").textContent=r.error?r.error:"Tersimpan di projects/"+PN+".json"},600)}
$("pj").onchange=()=>bdLoad($("pj").value);
$("pjnew").onclick=async()=>{const n=prompt("Nama proyek baru:");if(!n)return;PN=n;P=BLANK();await api("/api/project",{name:n,data:P});bdList(n.replace(/[^\w\- ]/g,"").trim())};
$("pjdel").onclick=async()=>{if(!confirm("Hapus proyek "+PN+"?"))return;await api("/api/project",{name:PN,delete:1});bdList()};
$("bscript").oninput=()=>{P.script=$("bscript").value;bdSave()};$("bstyle").oninput=()=>{P.style=$("bstyle").value;bdSave()};
document.querySelectorAll("[data-add]").forEach(b=>b.onclick=()=>{const k=b.dataset.add;
P[k].push(k=="panels"?{id:uid(),desc:"",shot:"Medium",cam:"Static",loc:"",chars:[],dur:5}:{id:uid(),name:"",desc:""});bdSave();bdRender()});
$("bbeats").onclick=()=>{const beats=P.script.split(/\n/).map(l=>l.match(/^\s*\d+[.)]\s*(.+)/)).filter(Boolean).map(m=>m[1].trim());
if(!beats.length)return alert("Tidak ada baris bernomor (1. 2. 3.) di script.");
if(P.panels.length&&!confirm("Tambahkan "+beats.length+" panel baru di bawah panel yang ada?"))return;
beats.forEach(t=>P.panels.push({id:uid(),desc:t,shot:"Medium",cam:"Static",loc:P.locs[0]?.id||"",chars:P.chars.map(c=>c.id),dur:5}));bdSave();bdRender()};
$("bstyle2").onclick=()=>{const t=[P.style&&"STYLE: "+P.style,P.chars.length&&"CHARACTERS: "+P.chars.map(c=>`"${c.name}", ${c.desc}`).join(" "),
P.locs.length&&"SETTING: "+P.locs.map(l=>`${l.name}: ${l.desc}`).join(" ")].filter(Boolean).join("\n");
$("style").value=t;store("style",t);tab("prod")};
function bdImg(it){if(it.img)return `<div class="img" onclick="lbox('${esc(it.img)}')"><img src="/outputs/${esc(it.img)}"></div>`;
const j=it.job&&last.find(x=>x.id==it.job);return `<div class="img">${j?(j.status=="error"?"Gagal: "+esc(j.error).slice(0,140):"Memproses…"):"Belum ada gambar"}</div>`}
function lbox(f){$("lbi").src="/outputs/"+f;$("lb").style.display="flex"}
function bdRender(){for(const k of ["chars","locs"])$("g-"+k).innerHTML=P[k].map((it,i)=>`<div class="it">${bdImg(it)}
<input placeholder="Nama" value="${esc(it.name)}" oninput="bdSet('${k}',${i},'name',this.value)">
<textarea placeholder="${k=="chars"?"3 ciri fisik, pakaian, sifat":"tempat, waktu, suasana, properti"}" oninput="bdSet('${k}',${i},'desc',this.value)">${esc(it.desc)}</textarea>
<div class="btns"><button onclick="bdGen('${k}',${i})">Generate gambar</button><button class="sec" onclick="bdDel('${k}',${i})" style="flex:0 0 auto;width:auto">Hapus</button></div></div>`).join("")||`<div class="hint">Belum ada. Klik "+ Tambah".</div>`;
$("g-panels").innerHTML=P.panels.map((it,i)=>`<div class="it"><b>Panel ${i+1}</b>${bdImg(it)}
<textarea placeholder="Aksi / apa yang terjadi" oninput="bdSet('panels',${i},'desc',this.value)">${esc(it.desc)}</textarea>
<div class="row"><select onchange="bdSet('panels',${i},'shot',this.value)">${SHOTS.map(s=>`<option ${s==it.shot?"selected":""}>${s}</option>`).join("")}</select>
<select onchange="bdSet('panels',${i},'cam',this.value)">${CAMS.map(s=>`<option ${s==it.cam?"selected":""}>${s}</option>`).join("")}</select></div>
<div class="row"><select onchange="bdSet('panels',${i},'loc',this.value)"><option value="">(lokasi)</option>${P.locs.map(l=>`<option value="${l.id}" ${l.id==it.loc?"selected":""}>${esc(l.name||"tanpa nama")}</option>`).join("")}</select>
<input type="number" min="1" max="15" value="${it.dur||5}" title="durasi (detik)" style="flex:0 0 64px" oninput="bdSet('panels',${i},'dur',+this.value)"></div>
<div class="tags">${P.chars.map(c=>`<label><input type="checkbox" style="width:auto" ${(it.chars||[]).includes(c.id)?"checked":""} onchange="bdChar(${i},'${c.id}',this.checked)">${esc(c.name||"?")}</label>`).join("")}</div>
<div class="btns"><button onclick="bdGen('panels',${i})">Sketsa</button><button class="sec" onclick="bdToStudio(${i})">Ke Production</button>
<button class="sec" onclick="bdMove(${i},-1)" style="flex:0 0 auto;width:auto" title="geser kiri">◀</button><button class="sec" onclick="bdMove(${i},1)" style="flex:0 0 auto;width:auto" title="geser kanan">▶</button>
<button class="sec" onclick="bdDel('panels',${i})" style="flex:0 0 auto;width:auto">✕</button></div></div>`).join("")||`<div class="hint">Belum ada panel. Tulis beats bernomor di script lalu klik "Pecah beats", atau "+ Panel".</div>`}
function bdSet(k,i,f,v){P[k][i][f]=v;bdSave()}
function bdChar(i,id,on){const a=P.panels[i].chars=(P.panels[i].chars||[]).filter(x=>x!=id);if(on)a.push(id);bdSave()}
function bdDel(k,i){if(!confirm("Hapus item ini?"))return;const id=P[k][i].id;P[k].splice(i,1);
if(k!="panels")P.panels.forEach(p=>{if(p.loc==id)p.loc="";p.chars=(p.chars||[]).filter(x=>x!=id)});bdSave();bdRender()}
function bdMove(i,d){const j=i+d;if(j<0||j>=P.panels.length)return;[P.panels[i],P.panels[j]]=[P.panels[j],P.panels[i]];bdSave();bdRender()}
async function bdGen(k,i){const it=P[k][i];if(!$("bwf").value)return alert("Pilih workflow gambar.");if(!(it.desc||"").trim())return alert("Isi deskripsinya dulu.");
const r=await api("/api/generate",{prompt:TPL[k](it,P),workflow:$("bwf").value,aspect:k=="chars"?"1:1":$("aspect").value||"9:16",resolution:"720p",duration:5,seed:-1});
if(r.error)return alert(r.error);it.job=r.id;it.img="";bdSave();await poll();bdRender()}
function bdJobs(jobs){let ch=false,wait=false;for(const k of ["chars","locs","panels"])for(const it of P[k]){if(!it.job||it.img)continue;const j=jobs.find(x=>x.id==it.job);
if(j&&j.status=="done"&&j.file){it.img=j.file;ch=true}else if(j)wait=true}
if(ch)bdSave();if((ch||wait)&&$("bd").style.display=="grid"&&!document.activeElement.closest?.(".it"))bdRender()}
function bdToStudio(i){const it=P.panels[i];$("prompt").value=`${it.shot} shot, camera ${it.cam}. ${it.desc} ${scene(it,P,false)}`.trim();
$("dur").value=it.dur||5;sync();tab("prod");$("prompt").focus()}
/* ---------------- LLM (Ollama) */
let LLM={};
async function llmStatus(){try{LLM=await api("/api/llm/status")}catch(e){LLM={}}const pl=LLM.pull||{};let h;
if(!LLM.ok)h=`<b style="color:#f87171">Ollama belum menyala</b><br>Penulis ide/script memakai Ollama (gratis, lokal). Pasang dari <b>ollama.com</b>, jalankan, lalu tunggu beberapa detik.`;
else if(!LLM.models.length)h=`<b>Ollama aktif${LLM.version?" (v"+esc(LLM.version)+")":""}, belum ada model.</b><br><button class="sec" onclick="llmPull()">Unduh ${LLM.recommended} (~5 GB)</button>`;
else h=`<b style="color:#4ade80">Ollama aktif</b> · model <select onchange="llmModel(this.value)">${LLM.models.map(m=>`<option ${m==LLM.model?"selected":""}>${esc(m)}</option>`).join("")}</select>`+
(LLM.models.some(m=>m.startsWith("qwen3"))?"":`<br><button class="sec" onclick="llmPull()">Unduh ${LLM.recommended} (disarankan)</button>`);
if(pl.active)h=h.replace(/<button[^>]*onclick="llmPull\(\)"[^>]*>.*?<\/button>/,"")+`<br>Mengunduh ${esc(pl.model)}: ${esc(pl.status)} ${pl.total?Math.round(100*pl.done/pl.total)+"% ("+(pl.done/1e9).toFixed(2)+" / "+(pl.total/1e9).toFixed(2)+" GB)":""}`;
else if(pl.model&&!pl.error&&LLM.models.includes(pl.model))h+=`<br><span style="color:#4ade80">${esc(pl.model)} selesai diunduh.</span>`;else if(pl.error)h+=`<br><span style="color:#f87171">${esc(pl.error)}</span>`;
if(LLM.ok&&!pl.active)h+=`<details style="margin-top:6px"><summary class="hint" style="cursor:pointer">Model lain / unduh manual</summary>
<div class="row" style="margin-top:6px"><input class="llmname" list="llmalt" value="${esc(LLM.recommended)}" style="width:100%;background:#16181d;color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:5px">
<button class="sec" style="flex:0 0 auto;width:auto;margin:0;padding:5px 10px" onclick="llmPull(this.previousElementSibling.value)">Unduh</button></div>
<datalist id="llmalt">${[LLM.recommended,...(LLM.alternatives||[])].map(m=>`<option value="${esc(m)}">`).join("")}</datalist>
<div class="hint" style="margin-top:4px">Atau di Command Prompt: <code>ollama pull ${esc(LLM.recommended)}</code>. Masalah? Jalankan <b>cek-ollama.bat</b> dan kirim hasilnya.</div></details>`;
$("llmbox1").innerHTML=$("llmbox2").innerHTML=h;if(pl.active)setTimeout(llmStatus,2000)}
async function llmPull(name){name=(typeof name=="string"&&name.trim())||LLM.recommended;document.querySelectorAll(".llm button").forEach(x=>{x.disabled=true;x.textContent="Memulai unduhan…"});
try{const r=await api("/api/llm/pull",{model:name});if(r.error)alert(r.error)}catch(e){alert("Gagal menghubungi aplikasi: "+e.message)}llmStatus()}
async function llmModel(m){await api("/api/llm/model",{model:m});llmStatus()}
async function llmRun(btn,msg,body){const old=btn.textContent;btn.disabled=true;btn.textContent="Menulis… (bisa 1-3 menit)";$(msg).textContent="";
try{const r=await api("/api/llm/run",body);if(r.error)throw new Error(r.error);$(msg).textContent="Ditulis oleh "+r._model+(r._warn?" · ⚠ "+r._warn:"");return r}
catch(e){$(msg).textContent="";alert(e.message);return null}finally{btn.disabled=false;btn.textContent=old}}
function navDone(){const ok={idea:!!P.story.trim(),scr:P.scenes.length>0,bd:P.chars.length+P.locs.length+P.panels.length>0,prod:false,edit:false};
document.querySelectorAll("nav [data-tab]").forEach(a=>a.classList.toggle("ok",!!ok[a.dataset.tab]))}

/* ---------------- 1. Ide */
const DEVF=["prompt","audience","genre","tone","lang","count"];
function devLoad(){DEVF.forEach(f=>$("d-"+f).value=P.dev[f]??"");$("d-storyline").value=P.story;devRender()}
DEVF.forEach(f=>$("d-"+f).oninput=$("d-"+f).onchange=()=>{P.dev[f]=$("d-"+f).value;bdSave()});
$("d-storyline").oninput=()=>{P.story=$("d-storyline").value;bdSave()};
function devRender(){$("d-ideas").innerHTML=P.dev.ideas.map((it,i)=>`<div class="it idea ${i==P.dev.chosen?"on":""}" onclick="devPick(${i})">
<input value="${esc(it.title)}" oninput="devSet(${i},'title',this.value)" onclick="event.stopPropagation()" style="font-weight:600">
<textarea oninput="devSet(${i},'logline',this.value)" onclick="event.stopPropagation()" title="Logline">${esc(it.logline)}</textarea>
<p><b style="font-size:12px">Hook 3 detik:</b></p><textarea oninput="devSet(${i},'hook',this.value)" onclick="event.stopPropagation()" style="height:54px">${esc(it.hook)}</textarea>
<span class="hint">${i==P.dev.chosen?"✓ Terpilih":"Klik untuk memilih"}</span></div>`).join("")||`<div class="hint">Belum ada ide. Tulis prompt di kiri lalu klik "Generate ide".</div>`}
function devSet(i,f,v){P.dev.ideas[i][f]=v;bdSave()}
function devPick(i){P.dev.chosen=i;bdSave();devRender()}
$("d-go").onclick=async()=>{if(!P.dev.prompt.trim())return alert("Tulis prompt ide dulu.");
const r=await llmRun($("d-go"),"d-msg",Object.assign({task:"ideas"},P.dev));if(!r)return;
P.dev.ideas=(r.ideas||[]).map(x=>({title:x.title||"",logline:x.logline||"",hook:x.hook||""}));P.dev.chosen=P.dev.ideas.length?0:-1;bdSave();devRender()};
$("d-story").onclick=async()=>{const it=P.dev.ideas[P.dev.chosen];if(!it)return alert("Pilih salah satu ide dulu.");
if(P.story.trim()&&!confirm("Ganti storyline yang sudah ada?"))return;
const r=await llmRun($("d-story"),"d-msg",Object.assign({task:"storyline",duration:P.target},P.dev,it));if(!r)return;
const cs=r.characters||[];P.story=[`JUDUL: ${r.title||it.title}`,`PREMIS: ${r.premise||""}`,"KARAKTER:",...cs.map(c=>`- ${c.name}: ${c.description}`),
`SETTING: ${r.setting||""}`,`AWAL: ${r.beginning||""}`,`TENGAH: ${r.middle||""}`,`AKHIR: ${r.end||""}`].join("\n");
if(!P.chars.length)P.chars=cs.map(c=>({id:uid(),name:c.name||"",desc:c.description||""}));  // benih untuk tab Breakdown
$("d-storyline").value=P.story;bdSave();bdRender()};
$("d-next").onclick=()=>tab("scr");

/* ---------------- 2. Script */
function scrSum(){const t=P.scenes.reduce((a,x)=>a+(+x.duration||0),0);$("s-sum").innerHTML=`Total: <span style="color:${t==P.target?"#4ade80":"#fbbf24"}">${t}</span> / ${P.target} detik · ${P.scenes.length} scene`}
function scrRender(){$("s-total").value=P.target;$("s-max").value=P.maxScene;
$("s-list").innerHTML=P.scenes.map((x,i)=>`<div class="sc"><div class="c"><b>Scene ${i+1}</b>
<label class="hint">Durasi (dtk)</label><input type="number" min="1" max="15" value="${x.duration||5}" oninput="scrSet(${i},'duration',+this.value)">
<label class="hint">Lokasi</label><input value="${esc(x.location)}" oninput="scrSet(${i},'location',this.value)">
<label class="hint">Waktu</label><input value="${esc(x.time)}" oninput="scrSet(${i},'time',this.value)">
<div class="btns"><button class="sec" onclick="scrMove(${i},-1)">↑</button><button class="sec" onclick="scrMove(${i},1)">↓</button><button class="sec" onclick="scrDel(${i})">✕</button></div></div>
<div class="c"><label class="hint">Aksi</label><textarea oninput="scrSet(${i},'action',this.value)">${esc(x.action)}</textarea>
<label class="hint">Dialog / VO</label><textarea oninput="scrSet(${i},'dialog',this.value)" style="height:48px">${esc(x.dialog)}</textarea>
<label class="hint">Teks di layar</label><input value="${esc(x.onscreen_text)}" oninput="scrSet(${i},'onscreen_text',this.value)"></div>
<div class="c"><label class="hint">Prompt visual (English, untuk model video)</label><textarea oninput="scrSet(${i},'visual',this.value)" style="height:150px">${esc(x.visual)}</textarea>
<div class="btns"><button onclick="scrToProd(${i})">Ke Production</button></div></div></div>`).join("")||`<div class="hint">Belum ada scene. Klik "Generate script dari storyline" atau "+ Scene".</div>`;scrSum()}
function scrSet(i,f,v){P.scenes[i][f]=v;bdSave();if(f=="duration")scrSum()}
function scrMove(i,d){const j=i+d;if(j<0||j>=P.scenes.length)return;[P.scenes[i],P.scenes[j]]=[P.scenes[j],P.scenes[i]];bdSave();scrRender()}
function scrDel(i){if(!confirm("Hapus scene "+(i+1)+"?"))return;P.scenes.splice(i,1);bdSave();scrRender()}
function scrToProd(i){const x=P.scenes[i];$("prompt").value=x.visual||x.action;$("dur").value=x.duration||5;sync();tab("prod");$("prompt").focus()}
$("s-total").onchange=()=>{P.target=+$("s-total").value;bdSave();scrSum()};$("s-max").oninput=()=>{P.maxScene=+$("s-max").value||8;bdSave()};
$("s-add").onclick=()=>{P.scenes.push({id:uid(),duration:5,location:"",time:"",action:"",dialog:"",onscreen_text:"",visual:""});bdSave();scrRender()};
$("s-go").onclick=async()=>{if(!P.story.trim())return alert("Storyline masih kosong. Buat dulu di tab Ide.");
if(P.scenes.length&&!confirm("Ganti semua scene yang sudah ada?"))return;
const r=await llmRun($("s-go"),"s-msg",{task:"script",storyline:P.story,duration:P.target,max_scene:P.maxScene,lang:P.dev.lang});if(!r)return;
P.scenes=(r.scenes||[]).map(x=>Object.assign({id:uid(),dialog:"",onscreen_text:""},x));bdSave();scrRender()};
$("s-bd").onclick=()=>{if(!P.scenes.length)return alert("Belum ada scene.");if(P.panels.length&&!confirm("Tambahkan "+P.scenes.length+" panel di bawah panel yang ada?"))return;
for(const x of P.scenes){let loc=P.locs.find(l=>l.name.trim().toLowerCase()==(x.location||"").trim().toLowerCase());
if(!loc&&x.location){loc={id:uid(),name:x.location,desc:x.time?"waktu: "+x.time:""};P.locs.push(loc)}
const txt=((x.action||"")+" "+(x.dialog||"")).toLowerCase();
P.panels.push({id:uid(),desc:x.action||"",shot:"Medium",cam:"Static",loc:loc?loc.id:"",chars:P.chars.filter(c=>c.name&&txt.includes(c.name.toLowerCase())).map(c=>c.id),dur:x.duration||5})}
bdSave();bdRender();tab("bd")};

init().then(()=>{bdList(store("pj"));tab(store("tab")||"idea")});
</script></body></html>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    load_history()
    port = CFG["app_port"]
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print("Seedance Studio: http://127.0.0.1:%d" % port, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
