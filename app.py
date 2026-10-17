#!/usr/bin/env python3
"""Seedance Shorts Studio: server lokal (UI di ui.html) -> ComfyUI / Ollama / ffmpeg.
Hanya pustaka standar Python."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python_embeded tidak otomatis memuat folder script
import comfy_detect
import llm
import render
import updater
import remote
import comfy_ws
import json, os, queue, random, re, shutil, socket, subprocess, sys, threading, time, uuid
import urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs")
WF = os.path.join(BASE, "workflows")
PROJ = os.path.join(BASE, "projects")
THUMBS = os.path.join(BASE, "cache", "styles")  # foto contoh gaya (Pexels), diunduh sekali
VTHUMBS = os.path.join(BASE, "cache", "thumbs")
REFS = os.path.join(BASE, "cache", "refs")  # gambar acuan dibuat persegi (kanvas sama) untuk node Seedream
FRAMES = os.path.join(BASE, "cache", "frames")  # frame terakhir tiap take (PNG penuh, untuk image-to-video)  # cuplikan JPG kecil dari video (pengganti <video> di daftar take)
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
THUMB_FAIL = {}  # pexels id -> waktu gagal terakhir (jangan coba ulang terus-menerus)  # breakdown pra-produksi: projects/<nama>.json
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
AUDIO_EXT = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".opus")
UI_FILE = os.path.join(BASE, "ui.html")
MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
        ".opus": "audio/ogg", ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".png": "image/png",
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
WORK = queue.Queue()   # job ComfyUI dikerjakan satu per satu (VRAM 8 GB; timeout dihitung saat job mulai)
BUSY = {"llm": 0, "render": 0}
BIND = {"host": "127.0.0.1"}   # 0.0.0.0 bila akses dari HP (Tailscale) aktif; filter IP di remote.kind()
LOGIN_HTML = """<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Seedance Studio - Masuk</title><style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0e0f12;color:#e8eaf0;font:16px system-ui,sans-serif}
form{background:#16181d;border:1px solid #262932;border-radius:14px;padding:24px;width:min(92vw,340px)}h1{font-size:18px;margin:0 0 4px}p{color:#8b90a0;font-size:13px;margin:0 0 16px}
input{width:100%;box-sizing:border-box;background:#0e0f12;color:#e8eaf0;border:1px solid #262932;border-radius:10px;padding:12px;font:inherit;font-size:20px;letter-spacing:4px;text-align:center}
button{width:100%;margin-top:12px;background:#ff8a3d;color:#1a0d00;border:0;border-radius:10px;padding:12px;font:inherit;font-weight:700}#m{color:#f87171;font-size:13px;margin-top:10px;min-height:1em}</style></head>
<body><form id="f"><h1>Seedance Studio</h1><p>Masukkan PIN yang diatur di PC (Pengaturan &#9881; &rarr; Akses dari HP).</p>
<input id="pin" type="password" inputmode="numeric" autocomplete="current-password" autofocus><button>Masuk</button><div id="m"></div></form>
<script>f.onsubmit=async e=>{e.preventDefault();const r=await fetch("/api/login",{method:"POST",headers:{"X-Studio":"1"},body:JSON.stringify({pin:pin.value})}).then(r=>r.json()).catch(()=>({error:"Tidak terhubung"}));
if(r.ok)location.reload();else{m.textContent=r.error||"PIN salah";pin.value=""}}</script></body></html>"""


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
# ComfyUI lokal: jangan lewat proxy sistem Windows. Python memakai proxy dari pengaturan Internet Windows
# (VPN/proxy) juga untuk http://127.0.0.1 bila tidak ada di daftar pengecualian -> ComfyUI dianggap mati.
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))
COMFY_STATE = os.path.join(BASE, "comfy.state.json")  # ditulis supervisor: sedang menyala / berhenti / tidak ditemukan
COMFY_LOG = os.path.join(BASE, "comfy.log")  # output ComfyUI dari supervisor
COMFY_RETRY = os.path.join(BASE, "comfy.retry")  # minta supervisor menyalakan ComfyUI sekarang


def http_json(url, data=None, timeout=15):
    req = urllib.request.Request(url, method="POST" if data is not None else "GET")
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with LOCAL.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


_EXTRA = {"t": 0.0, "ports": []}
_CU = {"t": 0.0, "url": None, "err": ""}
_CU_LOCK = threading.Lock()


def _alive(u, why=None):
    try:
        http_json(u + "/system_stats", timeout=4)
        return u
    except Exception as e:
        if why is not None:
            why.append("%s terbuka tapi tidak menjawab seperti ComfyUI (%s)" % (u.split("//")[-1], str(e)[:120]))
        return None


def _port_open(u):
    try:
        pu = urlparse(u)
        socket.create_connection((pu.hostname, pu.port or 80), timeout=0.5).close()
        return True
    except (OSError, ValueError):
        return False


def _find_comfy():
    last = _CU["url"]
    if last and _port_open(last):  # sudah pernah menjawab sebagai ComfyUI; sibuk generate = lambat menjawab, tetap hidup
        return last
    env = os.environ.get("COMFYUI_URL", "").rstrip("/")  # sama seperti backend Luminar
    cands = ([env] if env else []) + ["http://127.0.0.1:%d" % p for p in CFG["comfy_ports"]]
    why = []
    for u in cands:
        if _port_open(u) and _alive(u, why):
            return u
    _CU["err"] = "; ".join(why) or "port %s tertutup" % "/".join(str(p) for p in CFG["comfy_ports"])
    if time.time() - _EXTRA["t"] > 120:  # PowerShell itu berat: jarang-jarang saja
        _EXTRA["t"] = time.time()
        _EXTRA["ports"] = [r["port"] for r in comfy_detect.running_comfy()]
    for p in _EXTRA["ports"]:
        u = "http://127.0.0.1:%d" % p
        if u not in cands and _port_open(u) and _alive(u):
            return u
    return None


def comfy_info():
    """Keterangan untuk UI saat ComfyUI belum tersambung: status dari supervisor + akhir comfy.log."""
    info = {"state": "", "err": _CU["err"], "log": log_tail(COMFY_LOG, 8)}
    try:
        with open(COMFY_STATE, encoding="utf-8") as f:
            st = json.load(f)
        if time.time() - st.get("t", 0) < 30:  # supervisor masih hidup
            now = time.time()
            info.update(state=st.get("state", ""), code=st.get("code"),
                        secs=int(now - st["since"]) if st.get("since") else 0,
                        retry=int(max(0, st.get("retry_at", 0) - now)))
        else:
            info["state"] = "nosup"
    except (OSError, ValueError, KeyError):
        info["state"] = "nosup"
    return info


def comfy_url():
    """URL ComfyUI yang hidup, atau None (hasil disimpan 3 dtk). Cadangan: cari port dari proses ComfyUI yang
    sedang jalan (mis. dinyalakan aplikasi lain). Hanya satu thread yang mengecek; yang lain memakai hasil terakhir."""
    if time.time() - _CU["t"] < 3:
        return _CU["url"]
    if not _CU_LOCK.acquire(blocking=False):
        return _CU["url"]
    try:
        _CU.update(url=_find_comfy(), t=time.time())
    finally:
        _CU_LOCK.release()
    return _CU["url"]


KEY_FILE = os.path.join(BASE, "api_key.txt")
NODE = "ByteDanceTextToVideoNode"
SEEDREAM = "ByteDanceSeedreamNode"  # gambar dengan gambar acuan (storyboard yang mirip karakter/lokasi Breakdown)
I2V = "ByteDanceImageToVideoNode"  # frame pertama = frame terakhir scene sebelumnya (continuity antar klip)
_SPECS = {}  # node -> {"t", "base", "spec"}


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


def node_spec(base, node=NODE):
    """Input node Seedance menurut ComfyUI yang terpasang: {"names": set, "combos": {nama: [opsi]}} atau None."""
    if not base:
        return None
    _SPEC = _SPECS.setdefault(node, {"t": 0.0, "base": "", "spec": None})
    if _SPEC["base"] == base and time.time() - _SPEC["t"] < (300 if _SPEC["spec"] else 60):
        return _SPEC["spec"]
    try:
        info = http_json(base + "/object_info/" + node, timeout=10).get(node)
    except Exception:
        info = None
    if not info:
        _SPEC.update(t=time.time(), base=base, spec=None)  # node API belum terpasang: jangan ditanya tiap request
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


def build_graph(p, spec=None, image=None):
    """Workflow bawaan Seedance (format API): Text-to-Video, atau Image-to-Video bila `image` (nama file di folder
    input ComfyUI) = frame pertama."""
    inputs = {
        "model": p["model"], "prompt": p["prompt"], "resolution": p["resolution"],
        "aspect_ratio": p["aspect"], "duration": p["duration"], "seed": p["seed"],
        "camera_fixed": bool(p.get("camera_fixed")), "watermark": False,
    }
    if p.get("audio") and next((m for m in MODELS if m["id"] == p["model"]), {}).get("audio"):
        inputs["generate_audio"] = True
    if spec:  # kirim hanya input yang memang dimiliki node di ComfyUI ini
        models = spec["combos"].get("model")
        if models and inputs["model"] not in models:
            if not image:
                raise RuntimeError("Model %s tidak ada di ComfyUI ini. Pilihan: %s" % (inputs["model"], ", ".join(models)))
            # model ini tidak punya versi image-to-video (mis. lite): pakai model i2v terdekat
            inputs["model"] = next((m for m in models if "fast" in m), models[0])
        inputs = {k: v for k, v in inputs.items() if k in spec["names"]}
    if image:
        inputs["image"] = ["3", 0]
    graph = {
        "1": {"class_type": I2V if image else NODE, "inputs": inputs},
        "2": {"class_type": "SaveVideo", "inputs": {
            "video": ["1", 0], "filename_prefix": "video/seedance",
            "format": "auto", "codec": "auto"}},
    }
    if image:
        graph["3"] = {"class_type": "LoadImage", "inputs": {"image": image}}
    return graph


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
    ff = meta.get("first_frame")  # ["<node id>", "<nama input>"]: node yang menerima frame pertama
    if p.get("image") and ff and ff[0] in graph:
        graph["900"] = {"class_type": "LoadImage", "inputs": {"image": p["image"]}}
        graph[ff[0]]["inputs"][ff[1]] = ["900", 0]
    for k, up in enumerate(p.get("refs_up") or []):  # _studio.refs: [[node, input IMAGE], ...] = slot gambar acuan
        slots = meta.get("refs") or []
        if k >= len(slots) or slots[k][0] not in graph:
            break
        graph["91%d" % k] = {"class_type": "LoadImage", "inputs": {"image": up}}
        graph[slots[k][0]]["inputs"][slots[k][1]] = ["91%d" % k, 0]
    return graph


def seedream_size(aspect):
    """Ukuran piksel Seedream untuk aspek (~2,4 MP; tiap sisi >= 1024, kelipatan 32)."""
    m = re.match(r"^(\d+):(\d+)$", str(aspect or ""))
    ar = (int(m.group(1)) / int(m.group(2))) if m and int(m.group(2)) else 9 / 16
    w = max(1024, int(round((2_360_000 * ar) ** 0.5 / 32)) * 32)
    h = max(1024, int(round(w / ar / 32)) * 32)
    w = max(1024, int(round(h * ar / 32)) * 32)
    return w, h


def build_seedream(p, refs_up, spec):
    """Gambar dengan Seedream (cloud). refs_up = nama file di folder input ComfyUI (dikirim sebagai gambar acuan)."""
    w, h = seedream_size(p["aspect"])
    models = (spec["combos"].get("model") if spec else None) or []
    model = next((m for m in ("seedream-4-0-250828", "seedream-4-5-251128") if m in models), models[-1] if models else "seedream-4-0-250828")
    inputs = {"model": model, "prompt": p["prompt"], "size_preset": "Custom", "width": w, "height": h,
              "sequential_image_generation": "disabled", "max_images": 1, "seed": p["seed"], "watermark": False}
    if spec:
        inputs = {k: v for k, v in inputs.items() if k in spec["names"]}
    graph = {}
    last = None
    for k, up in enumerate(refs_up):
        graph["r%d" % k] = {"class_type": "LoadImage", "inputs": {"image": up}}
        if last is None:
            last = ["r0", 0]
        else:
            graph["b%d" % k] = {"class_type": "ImageBatch", "inputs": {"image1": last, "image2": ["r%d" % k, 0]}}
            last = ["b%d" % k, 0]
    if last:
        inputs["image"] = last
    graph["1"] = {"class_type": SEEDREAM, "inputs": inputs}
    graph["2"] = {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": "storyboard/seedream"}}
    return graph


def ref_path(name, square):
    """File acuan di outputs. square: kanvas persegi 1024 (letterbox putih) supaya beberapa gambar bisa digabung
    jadi satu batch tanpa terpotong."""
    src = out_path(name)
    if not square or not has_tool("ffmpeg"):
        return src
    dst = os.path.join(REFS, os.path.basename(src) + ".sq.png")
    if not os.path.exists(dst):
        os.makedirs(REFS, exist_ok=True)
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", src, "-vf",
                        "scale=1024:1024:force_original_aspect_ratio=decrease,pad=1024:1024:(ow-iw)/2:(oh-ih)/2:color=white",
                        "-frames:v", "1", dst], capture_output=True, timeout=60, creationflags=NOWIN)
    return dst if os.path.exists(dst) else src


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
    DL.update(active=True, error="", finished=[], index=0, count=len(models), overall=0)
    total_gb = sum(float(m.get("gb") or 0) for m in models) or 0
    done_gb = 0.0
    try:
        for i, m in enumerate(models, 1):
            DL["index"] = i
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
                        if total_gb:
                            DL["overall"] = min(99, int(100 * (done_gb + DL["done"] / 1e9) / total_gb))
            os.replace(part, dst)
            done_gb += float(m.get("gb") or 0)
            DL["finished"].append(m["file"])
    except Exception as e:
        DL["error"] = "Unduh %s gagal: %s (klik Unduh lagi untuk melanjutkan)" % (DL["file"], e)
    finally:
        DL.update(active=False, file="")


def find_videos(outputs):
    """File hasil: video lebih dulu, lalu audio, lalu gambar."""
    vids, auds, imgs = [], [], []
    for node in outputs.values():
        for items in node.values():
            if isinstance(items, list):
                for it in items:
                    fn = str(it.get("filename", "")).lower() if isinstance(it, dict) else ""
                    if fn.endswith(VIDEO_EXT):
                        vids.append(it)
                    elif fn.endswith(AUDIO_EXT) and it.get("type", "output") == "output":
                        auds.append(it)
                    elif fn.endswith(IMAGE_EXT) and it.get("type", "output") == "output":
                        imgs.append(it)
    return vids or auds or imgs


def free_ollama():
    """VRAM 8 GB: keluarkan model Ollama (sisa menulis script/breakdown) sebelum ComfyUI memakai GPU."""
    if BUSY["llm"]:
        return
    base = llm_base()
    try:
        with llm._req(base + "/api/ps", timeout=3) as r:
            names = [m.get("name") or m.get("model") for m in json.loads(r.read().decode()).get("models", [])]
        for n in filter(None, names):
            with llm._req(base + "/api/generate", {"model": n, "keep_alive": 0}, timeout=20) as r:
                r.read()
    except Exception:
        pass


def last_frame(name):
    """PNG frame terakhir sebuah video di outputs (gambar: dikembalikan apa adanya). Dibuat sekali lewat ffmpeg."""
    src = out_path(name)
    if src.lower().endswith(IMAGE_EXT):
        return src
    if not has_tool("ffmpeg"):
        raise RuntimeError("ffmpeg dibutuhkan untuk mengambil frame terakhir scene sebelumnya (pasang ffmpeg).")
    dst = os.path.join(FRAMES, os.path.basename(src) + ".last.png")
    if os.path.exists(dst):
        return dst
    os.makedirs(FRAMES, exist_ok=True)
    tmp = "%s.%d.tmp.png" % (dst, threading.get_ident())
    for seek in (["-sseof", "-0.6"], []):  # -update 1: tiap frame menimpa file -> tersisa frame terakhir
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y"] + seek + ["-i", src, "-an",
                        "-update", "1", tmp], capture_output=True, timeout=120, creationflags=NOWIN)
        if os.path.exists(tmp) and os.path.getsize(tmp):
            os.replace(tmp, dst)
            return dst
    raise RuntimeError("Tidak bisa mengambil frame terakhir dari %s." % name)


def frame_thumb(name):
    """JPG kecil frame terakhir (untuk ditampilkan di UI). None bila tidak bisa."""
    try:
        png = last_frame(name)
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    dst = os.path.join(VTHUMBS, os.path.basename(name) + ".last.jpg")
    if not os.path.exists(dst):
        os.makedirs(VTHUMBS, exist_ok=True)
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", png, "-vf", "scale=360:-2",
                        "-q:v", "5", dst], capture_output=True, timeout=30, creationflags=NOWIN)
    return dst if os.path.exists(dst) else None


def comfy_upload(base, path):
    """Unggah gambar ke folder input ComfyUI (POST /upload/image, multipart). Return nama untuk LoadImage."""
    bnd = uuid.uuid4().hex
    name = "studio_" + re.sub(r"[^\w.\-]", "_", os.path.basename(path))
    with open(path, "rb") as f:
        data = f.read()
    part = lambda n, v: b"--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (bnd.encode(), n, v)
    body = (b"--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
            % (bnd.encode(), name.encode(), b"image/png" if name.lower().endswith(".png") else b"image/jpeg")
            + data + b"\r\n" + part(b"type", b"input") + part(b"overwrite", b"true") + b"--%s--\r\n" % bnd.encode())
    req = urllib.request.Request(base + "/upload/image", data=body, method="POST",
                                 headers={"Content-Type": "multipart/form-data; boundary=" + bnd})
    with LOCAL.open(req, timeout=60) as r:
        res = json.loads(r.read().decode())
    return (res["subfolder"] + "/" if res.get("subfolder") else "") + res["name"]


def first_source(job):
    """Nama file yang frame terakhirnya jadi frame pertama job ini. None = scene sebelumnya masih dikerjakan
    (job dimasukkan lagi ke belakang antrean)."""
    p = job["params"]
    if not p.get("first_job"):
        return p.get("first_file") or None
    dep = JOBS.get(p["first_job"])
    if not dep:
        raise RuntimeError("Take scene sebelumnya tidak ditemukan (aplikasi sempat restart). Generate ulang scene ini.")
    if dep["status"] in ("queued", "running"):
        job.pop("started", None)
        job["progress"] = {"pct": 0, "stage": "Menunggu scene sebelumnya"}
        time.sleep(1)
        WORK.put(job)
        return None
    if dep["status"] == "cancelled":
        raise RuntimeError("Scene sebelumnya dibatalkan, jadi scene ini tidak bisa disambung. Buat scene sebelumnya lagi, atau pilih 'Teks saja'.")
    if dep["status"] != "done" or not dep.get("file"):
        raise RuntimeError("Scene sebelumnya gagal dibuat, jadi scene ini tidak bisa disambung. Ulangi scene sebelumnya dulu.")
    return dep["file"]


def run_job(job):
    prog = None
    job["started"] = time.time()
    job["progress"] = {"pct": 0, "stage": "Menyiapkan"}

    def chk():
        if job.get("cancel"):
            raise Cancelled()
    try:
        chk()
        base = comfy_url()
        if not base:
            raise RuntimeError("ComfyUI belum menyala. Tunggu sebentar atau cek studio.log.")
        p = job["params"]
        if p.get("workflow"):
            missing = [m["file"] for m in (model_status(base, wf_meta(p["workflow"])) or []) if not m["present"]]
            if missing:
                raise RuntimeError("Model belum ada di ComfyUI: %s -> Klik 'Unduh model yang kurang' di kotak model (kolom kiri tahap ini), lalu ulangi." % ", ".join(missing))
            free_ollama()  # model lokal berjalan di GPU sendiri (Seedance cloud tidak perlu)
        image = None
        if p.get("first_job") or p.get("first_file"):  # continuity: frame terakhir scene sebelumnya
            src = first_source(job)
            if src is None:
                return
            chk()
            if p.get("workflow") and not wf_meta(p["workflow"]).get("first_frame"):
                job["note"] = "Workflow ini tidak menerima frame pertama; dibuat dari teks saja."
            else:
                job["progress"] = {"pct": 0, "stage": "Mengambil frame terakhir scene sebelumnya"}
                image = comfy_upload(base, last_frame(src))
                job["first_used"] = src
        refs_up = []
        if p.get("refs"):  # gambar acuan (karakter/lokasi dari Breakdown) -> folder input ComfyUI
            job["progress"] = {"pct": 0, "stage": "Mengunggah gambar acuan"}
            for f in p["refs"][:10]:
                refs_up.append(comfy_upload(base, ref_path(f, bool(p.get("seedream")))))
            chk()
        if p.get("seedream"):
            spec = node_spec(base, SEEDREAM)
            if not spec:
                raise RuntimeError("Node %s tidak ada di ComfyUI ini (update ComfyUI). Pilih workflow gambar lokal di tab Storyboard." % SEEDREAM)
            graph = build_seedream(p, refs_up, spec)
        elif p.get("workflow"):
            graph = custom_graph(p["workflow"], dict(p, image=image, refs_up=refs_up))
        else:
            spec = node_spec(base, I2V if image else NODE)
            if image and not spec:
                raise RuntimeError("Node %s tidak ada di ComfyUI ini (update ComfyUI), jadi scene tidak bisa disambung "
                                   "dari frame terakhir. Pilih 'Teks saja' di Frame pertama." % I2V)
            graph = build_graph(p, spec, image)
        job["status"] = "queued"
        job["progress"] = {"pct": 0, "stage": "Mengirim ke ComfyUI"}
        try:  # progres per node/step lewat websocket ComfyUI (opsional)
            prog = comfy_ws.Progress(base, job["id"], graph, job)
        except Exception:
            prog = None
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
        job["prompt_id"] = pid
        if prog:
            prog.pid = pid
        job["status"] = "running"
        if job.get("cancel"):  # dibatalkan selagi dikirim
            _stop_comfy(job)
            raise Cancelled()
        timeout = wf_meta(p["workflow"]).get("timeout") if p.get("workflow") else None
        deadline = time.time() + max(CFG["job_timeout_seconds"], int(timeout or 0))
        while time.time() < deadline:
            for _ in range(max(1, int(CFG["poll_seconds"] * 4))):  # tidur pendek: batal terasa cepat
                if job.get("cancel"):
                    break
                time.sleep(0.25)
            chk()
            h = http_json(base + "/history/" + pid, timeout=15).get(pid)
            if not h:
                if job["progress"].get("pct", 0) <= 1:  # belum ada event: masih antre di ComfyUI (mis. dipakai aplikasi lain)?
                    try:
                        q = http_json(base + "/queue", timeout=5)
                        if any(len(x) > 1 and x[1] == pid for x in q.get("queue_pending", [])):
                            job["progress"] = {"pct": 0, "stage": "Menunggu antrean ComfyUI"}
                        elif job["progress"].get("stage") in ("Mengirim ke ComfyUI", "Menunggu antrean ComfyUI"):
                            job["progress"] = {"pct": 1, "stage": "Memproses"}
                    except Exception:
                        pass
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
                job["progress"] = {"pct": 99, "stage": "Mengambil hasil"}
                with LOCAL.open(url, timeout=120) as r, open(os.path.join(OUT, name), "wb") as f:
                    shutil.copyfileobj(r, f)
                job["file"] = name
                job["progress"] = {"pct": 100, "stage": "Selesai"}
                job["status"] = "done"
                save_meta(job)
                return
        try:  # batalkan job macet supaya antrian ComfyUI tidak tersumbat
            http_json(base + "/queue", {"delete": [pid]}, timeout=10)
            http_json(base + "/interrupt", {}, timeout=10)
        except Exception:
            pass
        raise RuntimeError("Timeout menunggu hasil dari ComfyUI (job dibatalkan).")
    except Cancelled:
        job.update(status="cancelled", error="Dibatalkan.", progress={"pct": 0, "stage": "Dibatalkan"})
    except Exception as e:
        if job.get("cancel"):  # error akibat interrupt: tetap dianggap batal
            job.update(status="cancelled", error="Dibatalkan.", progress={"pct": 0, "stage": "Dibatalkan"})
            return
        msg = str(e)
        low = msg.lower()
        if any(w in low for w in ("unauthorized", "login", "api key", "401", "authenticat")):
            msg += " -> Isi API key akun Comfy di bagian Pengaturan (buat di platform.comfy.org)."
        elif "credit" in low or "balance" in low or "402" in low:
            msg += " -> Kredit akun Comfy habis/kurang."
        job["status"] = "error"
        job["error"] = msg
    finally:
        if prog:
            prog.close()


class Cancelled(Exception):
    pass


PROCS = {}  # id job render -> proses ffmpeg (untuk dimatikan saat dibatalkan)


def _stop_comfy(job):
    """Hentikan prompt job ini di ComfyUI: hapus dari antrean, dan interrupt HANYA bila job kita yang sedang jalan
    (jangan mematikan pekerjaan aplikasi lain yang memakai ComfyUI yang sama)."""
    pid, base = job.get("prompt_id"), comfy_url()
    if not pid or not base:
        return
    try:
        q = http_json(base + "/queue", timeout=5)
        running = any(len(x) > 1 and x[1] == pid for x in q.get("queue_running", []))
        if not running:
            http_json(base + "/queue", {"delete": [pid]}, timeout=5)
        else:
            http_json(base + "/interrupt", {"prompt_id": pid}, timeout=5)
    except Exception:
        pass


def cancel_job(jid):
    """Batalkan job: antre -> dilewati worker; berjalan -> ComfyUI di-interrupt / ffmpeg dimatikan.
    True bila ada yang dibatalkan."""
    job = JOBS.get(jid)
    if not job or job["status"] not in ("queued", "running"):
        return False
    job["cancel"] = True
    job["progress"] = {"pct": job.get("progress", {}).get("pct", 0), "stage": "Membatalkan"}
    p = PROCS.get(jid)
    if p:  # render ffmpeg
        try:
            p.kill()
        except OSError:
            pass
    elif job.get("prompt_id"):  # sudah dikirim ke ComfyUI
        threading.Thread(target=_stop_comfy, args=(job,), daemon=True).start()
    if not job.get("started"):  # masih antre lokal: langsung ditandai, worker akan melewatinya
        job.update(status="cancelled", error="Dibatalkan.", progress={"pct": 0, "stage": "Dibatalkan"})
    return True


def worker():
    while True:
        job = WORK.get()
        try:
            if job.get("cancel") or job["status"] == "cancelled":
                job.update(status="cancelled", error="Dibatalkan.", progress={"pct": 0, "stage": "Dibatalkan"})
            else:
                run_job(job)
        finally:
            WORK.task_done()


def busy():
    with LOCK:
        jobs = any(j["status"] in ("queued", "running") for j in JOBS.values())
    return jobs or BUSY["llm"] > 0 or BUSY["render"] > 0 or DL["active"] or llm.PULL["active"]


def log_tail(path=None, n=4):
    """Baris terakhir log tanpa membaca seluruh file (bisa sampai 5 MB)."""
    try:
        with open(path or os.path.join(BASE, "studio.log"), "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            lines = [x for x in f.read().decode("utf-8", "replace").replace("\r", "\n").splitlines() if x.strip()]
            return "\n".join(lines[-n:])
    except OSError:
        return ""


_WHICH = {}


def has_tool(name):
    """shutil.which dengan cache 60 dtk (dipanggil tiap /api/status)."""
    t, v = _WHICH.get(name, (0.0, False))
    if time.time() - t > 60:
        v = bool(shutil.which(name))
        _WHICH[name] = (time.time(), v)
    return v


def jobs_view(keep=None):
    """Job (terbaru dulu) + posisi antrean & waktu berjalan. keep(job) -> bool menyaring."""
    with LOCK:
        jobs = sorted(JOBS.values(), key=lambda j: j["created"], reverse=True)
    waiting = [j for j in reversed(jobs) if j["status"] == "queued" and not j.get("started")]
    for n, j in enumerate(waiting, 1):
        j["progress"] = {"pct": 0, "stage": "Antre ke-%d" % n}
    now = time.time()
    for j in jobs:
        if j.get("started") and j["status"] in ("queued", "running"):
            j["elapsed"] = int(now - j["started"])
    return [j for j in jobs if keep is None or keep(j)]


THUMB_SEM = threading.Semaphore(2)
THUMB_BAD = set()


def video_thumb(name):
    """Path JPG kecil (lebar 360) dari frame ke-0.5 dtk sebuah video di outputs, dibuat sekali. None bila tidak bisa."""
    try:
        src = out_path(name)
    except RuntimeError:
        return None
    if not src.lower().endswith(VIDEO_EXT) or src in THUMB_BAD or not has_tool("ffmpeg"):
        return None
    dst = os.path.join(VTHUMBS, os.path.basename(src) + ".jpg")
    if os.path.exists(dst):
        return dst
    with THUMB_SEM:
        if os.path.exists(dst):  # sudah dibuat thread lain
            return dst
        os.makedirs(VTHUMBS, exist_ok=True)
        tmp = "%s.%d.tmp.jpg" % (dst, threading.get_ident())
        for ss in (["-ss", "0.5"], []):  # klip < 0.5 dtk: frame pertama
            try:
                subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y"] + ss + ["-i", src, "-frames:v", "1",
                                "-vf", "scale=360:-2", "-q:v", "5", tmp], capture_output=True, timeout=30,
                               creationflags=NOWIN)
            except (OSError, subprocess.SubprocessError):
                break
            if os.path.exists(tmp) and os.path.getsize(tmp):
                os.replace(tmp, dst)
                return dst
        try:
            os.remove(tmp)
        except OSError:
            pass
        THUMB_BAD.add(src)
    return None


def save_meta(job):
    meta = {k: job[k] for k in ("id", "params", "file", "created")}
    if job.get("first_used"):
        meta["first_used"] = job["first_used"]
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
    wf = os.path.basename(d["workflow"]) if d.get("workflow") else ""
    meta = wf_meta(wf) if wf else {}
    lo = 1 if wf else (m["min_dur"] if m else 3)
    dur = max(lo, min(int(meta.get("max_duration", 15)), int(round(float(d.get("duration", 5))))))
    seed = int(d.get("seed", -1))
    if seed < 0:
        seed = random.randint(0, 2**31 - 1)
    return {
        "prompt": prompt, "scene": scene, "model": model, "duration": dur, "seed": seed,
        "aspect": str(d.get("aspect") or "9:16")[:20],          # opsi sebenarnya divalidasi ComfyUI
        "resolution": str(d.get("resolution") or "720p")[:20],
        "audio": bool(d.get("audio")), "camera_fixed": bool(d.get("camera_fixed")),
        "workflow": wf, "ref": str(d.get("ref", ""))[:80],
        # frame pertama: file hasil (video -> frame terakhirnya, gambar -> apa adanya) atau job yang belum selesai
        "refs": [os.path.basename(str(x)) for x in (d.get("refs") or [])][:10], "seedream": bool(d.get("seedream")),
        "first_file": os.path.basename(str(d.get("first_file") or "")), "first_job": str(d.get("first_job") or "")[:40],
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
    if cb and not busy:  # VRAM 8 GB: kosongkan model ComfyUI hanya bila VRAM memang kurang untuk LLM
        try:
            dev = (http_json(cb + "/system_stats", timeout=3).get("devices") or [{}])[0]
            need = dev.get("type") == "cuda" and dev.get("vram_free", 0) < 6.5e9  # qwen3:8b butuh ~6 GB
        except Exception:
            need = True
        if need:
            try:
                http_json(cb + "/free", {"unload_models": True, "free_memory": True}, timeout=5)
            except Exception:
                pass
    task = {"ideas": llm.ideas, "storyline": llm.storyline, "script": llm.script,
            "breakdown": llm.breakdown, "dialog": llm.dialog, "continuity": llm.continuity}.get(d.get("task"))
    if not task:
        raise ValueError("Tugas LLM tidak dikenal.")
    BUSY["llm"] += 1
    try:
        res = task(base, model, d)
    finally:
        BUSY["llm"] -= 1
    res["_model"] = model
    return res


def out_path(name):
    name = os.path.basename(str(name or ""))
    p = os.path.join(OUT, name)
    if not name or not os.path.isfile(p):
        raise RuntimeError("File tidak ditemukan: %s" % name)
    return p


def start_render(d):
    """Render final (tahap Editing) di thread terpisah; status lewat JOBS seperti job lain."""
    clips = [dict(path=out_path(c.get("file")), start=c.get("start", 0), end=c.get("end", 0), text=c.get("text", ""),
                  tr=str(c.get("tr") or ""))
             for c in d.get("clips", [])]
    name = "final_%s.mp4" % time.strftime("%Y%m%d-%H%M%S")
    spec = {"clips": clips, "transition": d.get("transition", "cut"), "fade": d.get("fade", 0.5),
            "clip_audio": bool(d.get("clip_audio", True)), "clip_vol": float(d.get("clip_vol", 1)),
            "music": out_path(d["music"]) if d.get("music") else "", "music_vol": float(d.get("music_vol", 0.3)), "duck": bool(d.get("duck", True)),
            "subtitles": bool(d.get("subtitles")), "out": os.path.join(OUT, name),
            "cancelled": lambda: job.get("cancel")}
    job = {"id": uuid.uuid4().hex, "params": {"prompt": "Render final (%d klip)" % len(clips), "kind": "render",
           "ref": str(d.get("ref", ""))[:80]}, "status": "running", "file": "", "error": "", "created": time.time()}
    with LOCK:
        JOBS[job["id"]] = job

    def go():
        BUSY["render"] += 1
        job["started"] = time.time()
        job["progress"] = {"pct": 0, "stage": "Menyiapkan klip"}
        try:
            os.makedirs(OUT, exist_ok=True)
            render.render(spec, progress=lambda pct: job.update(progress={"pct": pct, "stage": "Merender"}),
                          on_proc=lambda p: (PROCS.__setitem__(job["id"], p), job.get("cancel") and p.kill()))
            if job.get("cancel"):
                raise Cancelled()
            job["progress"] = {"pct": 100, "stage": "Selesai"}
            job.update(file=name, status="done")
            save_meta(job)
        except Exception as e:
            if job.get("cancel") or isinstance(e, Cancelled):
                job.update(status="cancelled", error="Dibatalkan.", progress={"pct": 0, "stage": "Dibatalkan"})
                try:
                    os.remove(os.path.join(OUT, name))
                except OSError:
                    pass
            else:
                job.update(status="error", error=str(e))
        finally:
            PROCS.pop(job["id"], None)
            BUSY["render"] -= 1
    threading.Thread(target=go, daemon=True).start()
    return job


def style_thumb(pid):
    """Path foto contoh gaya dari Pexels (cache lokal; unduh bila belum ada). None bila gagal."""
    pid = str(pid)
    if not pid.isdigit():
        return None
    path = os.path.join(THUMBS, pid + ".jpg")
    if os.path.isfile(path):
        return path
    if time.time() - THUMB_FAIL.get(pid, 0) < 600:
        return None
    url = "https://images.pexels.com/photos/%s/pexels-photo-%s.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=640&w=360" % (pid, pid)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SeedanceStudio)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read(3 * 1024 * 1024)
        if not data.startswith(b"\xff\xd8") or len(data) < 2000:  # harus JPEG sungguhan
            raise ValueError("bukan jpeg")
        os.makedirs(THUMBS, exist_ok=True)
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(path + ".tmp", path)
        return path
    except Exception:
        THUMB_FAIL[pid] = time.time()
        return None


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
class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return  # browser menutup koneksi (mis. preview video); bukan error
        super().handle_error(request, client_address)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200, headers=()):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _gate(self, post=False):
        """Siapa yang boleh masuk: PC sendiri, atau perangkat Tailscale yang sudah login PIN.
        Return 'local' / 'remote' / 'login' (belum login, boleh ke /api/login) / None (sudah dijawab)."""
        k = remote.kind(self.client_address[0], CFG)
        if not k or not remote.host_ok(self.headers.get("Host"), k):  # Host asing = DNS-rebinding
            self.send_json({"error": "forbidden"}, 403)
            return None
        if post and self.headers.get("X-Studio") != "1":  # header khusus: halaman web lain tidak bisa mengirim (CSRF)
            self.send_json({"error": "forbidden"}, 403)
            return None
        if k == "remote" and not remote.authed(self.headers.get("Cookie"), CFG):
            path = urlparse(self.path).path
            if post and path == "/api/login":
                return "login"
            if not post and path == "/":
                b = LOGIN_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return None
            self.send_json({"error": "login"}, 401)
            return None
        return k

    def do_GET(self):
        self.who = self._gate()
        if not self.who:
            return
        u = urlparse(self.path)
        if u.path == "/":
            try:
                with open(UI_FILE, "rb") as f:
                    b = f.read()
            except OSError:
                b = b"ui.html tidak ditemukan. Jalankan update.bat."
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif u.path in ("/styles.js",):  # file statis UI
            with open(os.path.join(BASE, u.path.lstrip("/")), "rb") as f:
                b = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif u.path == "/api/stylethumb":
            path = style_thumb(parse_qs(u.query).get("pid", [""])[0])
            if not path:
                return self.send_json({"error": "tidak tersedia"}, 404)
            with open(path, "rb") as f:
                b = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "max-age=604800")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif u.path == "/api/config":
            names = sorted(f for f in os.listdir(WF) if f.endswith(".json")) if os.path.isdir(WF) else []
            wfs = [{"file": f, "label": wf_meta(f).get("label") or f, "note": wf_meta(f).get("note", ""),
                    "kind": wf_meta(f).get("kind", "video"), "max_duration": wf_meta(f).get("max_duration", 15),
                    "audio": bool(wf_meta(f).get("audio")), "first_frame": bool(wf_meta(f).get("first_frame")), "refs": len(wf_meta(f).get("refs") or [])}
                   for f in names]
            spec = node_spec(comfy_url())
            cb = spec["combos"] if spec else {}
            i2v = node_spec(comfy_url(), I2V)
            self.send_json({"models": model_list(spec), "aspects": cb.get("aspect_ratio") or ASPECTS,
                            "resolutions": cb.get("resolution") or RESOLUTIONS, "live": bool(spec),
                            "seedream": bool(node_spec(comfy_url(), SEEDREAM)), "i2v": bool(i2v), "i2v_models": (i2v or {}).get("combos", {}).get("model") or [],
                            "workflows": wfs})
        elif u.path == "/api/busy":
            self.send_json({"busy": busy()})
        elif u.path == "/api/status":
            cu = comfy_url()
            self.send_json({"comfy": bool(cu), "comfy_info": None if cu else comfy_info(),
                            "ffmpeg": has_tool("ffmpeg"), "log": log_tail(), "dl": DL,
                            "has_key": bool(api_key()), "version": updater.local_version()[:7],
                            "branch": updater.branch(), "auto_update": CFG.get("auto_update", True),
                            "remote": self.who == "remote"})
        elif u.path == "/api/remote":
            if self.who != "local":
                return self.send_json({"error": "Hanya bisa diatur dari PC."}, 403)
            ts = remote.tailscale()
            port = CFG["app_port"]
            urls = ["http://%s:%d" % (h, port) for h in ([ts["name"]] if ts["name"] else []) + ts["ips"]]
            self.send_json({"enabled": bool(CFG.get("remote_access")), "has_pin": bool(CFG.get("remote_pin_hash")),
                            "listening": BIND["host"] != "127.0.0.1", "port": port, "tailscale": ts, "urls": urls})
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
        elif u.path == "/api/llm/progress":
            self.send_json(llm.PROG)
        elif u.path == "/api/jobs":
            self.send_json(jobs_view())
        elif u.path == "/api/lastframe":
            path = frame_thumb(parse_qs(u.query).get("f", [""])[0])
            if not path:
                return self.send_json({"error": "tidak tersedia"}, 404)
            with open(path, "rb") as f:
                b = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "private, max-age=604800")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif u.path == "/api/thumb":
            path = video_thumb(parse_qs(u.query).get("f", [""])[0])
            if not path:
                return self.send_json({"error": "tidak tersedia"}, 404)
            with open(path, "rb") as f:
                b = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "private, max-age=604800")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
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
        self.send_header("Cache-Control", "private, max-age=86400")  # nama file hasil selalu unik (waktu + id)
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
        self.who = self._gate(post=True)
        if not self.who:
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            u = urlparse(self.path)
            if u.path == "/api/login":
                ip = self.client_address[0]
                if self.who != "login":
                    return self.send_json({"ok": True})
                if remote.locked(ip):
                    return self.send_json({"error": "Terlalu banyak PIN salah. Coba lagi 5 menit lagi."}, 429)
                d = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
                if remote.check_pin(d.get("pin"), CFG):
                    return self.send_json({"ok": True}, headers=[("Set-Cookie", remote.cookie(CFG))])
                remote.failed(ip)
                return self.send_json({"error": "PIN salah."}, 401)
            if u.path == "/api/logout":
                return self.send_json({"ok": True}, headers=[("Set-Cookie", remote.cookie(CFG, clear=True))])
            if u.path == "/api/upload":  # body = isi file mentah
                name = os.path.basename(parse_qs(u.query).get("name", ["file"])[0])
                ext = os.path.splitext(name)[1].lower()
                if ext not in AUDIO_EXT + VIDEO_EXT + IMAGE_EXT or n > 500 * 1024 * 1024:
                    raise ValueError("File harus audio/video/gambar, maks 500 MB.")
                dst = "upload_%s_%s" % (time.strftime("%Y%m%d-%H%M%S"), re.sub(r"[^\w.\-]", "_", name))
                os.makedirs(OUT, exist_ok=True)
                left = n
                with open(os.path.join(OUT, dst), "wb") as f:
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                return self.send_json({"file": dst})
            d = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/remote":
                if self.who != "local":
                    return self.send_json({"error": "Hanya bisa diatur dari PC."}, 403)
                if d.get("pin"):
                    save_cfg(**remote.pin_fields(d["pin"]))
                if "enabled" in d:
                    if d["enabled"] and not CFG.get("remote_pin_hash"):
                        raise ValueError("Atur PIN dulu (minimal 6 karakter).")
                    save_cfg(remote_access=bool(d["enabled"]))
                want = "0.0.0.0" if CFG.get("remote_access") and CFG.get("remote_pin_hash") else "127.0.0.1"
                restart = want != BIND["host"]
                if restart:  # ganti alamat dengar: keluar, supervisor menyalakan app.py lagi dalam ~5 dtk
                    threading.Timer(1.0, os._exit, [3]).start()
                return self.send_json({"ok": True, "restart": restart})
            if self.path == "/api/jobs/query":  # polling UI: hanya job yang ditunggu proyek ini + yang sedang aktif
                ids = set(map(str, d.get("ids") or []))
                return self.send_json(jobs_view(lambda j: j["id"] in ids or j["status"] in ("queued", "running")))
            if self.path == "/api/cancel":  # {id} | {ids:[]} | {all:true} ; {llm:true} menghentikan penulisan AI
                ids = [str(x) for x in (d.get("ids") or [])] + ([str(d["id"])] if d.get("id") else [])
                if d.get("all"):
                    with LOCK:
                        ids = [k for k, j in JOBS.items() if j["status"] in ("queued", "running")]
                n = sum(1 for k in ids if cancel_job(k))
                if (d.get("llm") or d.get("all")) and llm.PROG.get("active"):
                    llm.CANCEL["on"] = True
                    n += 1
                return self.send_json({"ok": True, "cancelled": n})
            if self.path == "/api/render":
                self.send_json(start_render(d))
            elif self.path == "/api/update/check":
                sha = updater.latest()
                self.send_json({"latest": sha[:7], "current": updater.local_version()[:7],
                                "available": bool(sha) and sha != updater.local_version()})
            elif self.path == "/api/generate":
                p = clean_params(d)
                job = {"id": uuid.uuid4().hex, "params": p, "status": "queued", "file": "",
                       "error": "", "created": time.time()}
                with LOCK:
                    JOBS[job["id"]] = job
                WORK.put(job)
                self.send_json(job)
            elif self.path == "/api/comfy/save":
                m = re.match(r"^(?:https?://)?(?:127\.0\.0\.1|localhost)?:?(\d{2,5})/?$", (d.get("path") or "").strip())
                if m:  # user memasukkan port / URL ComfyUI yang sudah jalan
                    port = int(m.group(1))
                    if not _alive("http://127.0.0.1:%d" % port):
                        raise RuntimeError("Tidak ada ComfyUI yang menjawab di port %d." % port)
                    save_cfg(comfy_ports=[port] + [x for x in CFG["comfy_ports"] if x != port])
                    _CU["t"] = 0
                    return self.send_json({"cmd": "port %d" % port, "cwd": ""})
                r = comfy_detect.resolve(d.get("path", "")) if d.get("path") else None
                if not r:
                    cmd, cwd = comfy_detect.detect({})
                    r = (cmd, cwd) if cmd else None
                if not r:
                    raise RuntimeError("ComfyUI tidak ditemukan di lokasi itu. Pilih ComfyUI.exe atau folder yang berisi main.py.")
                save_cfg(comfy_cmd=r[0], comfy_cwd=r[1] or "")
                self.send_json({"cmd": r[0], "cwd": r[1] or ""})
            elif self.path == "/api/comfy/restart":  # supervisor membaca file ini dalam <= 5 dtk
                with open(COMFY_RETRY, "w") as f:
                    f.write(str(time.time()))
                _CU["t"] = 0
                self.send_json({"ok": True})
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
                for fp in (os.path.join(OUT, name), os.path.join(OUT, name + ".json"), os.path.join(VTHUMBS, name + ".jpg"),
                           os.path.join(VTHUMBS, name + ".last.jpg"), os.path.join(FRAMES, name + ".last.png")):
                    try:
                        os.remove(fp)
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




def main():
    os.makedirs(OUT, exist_ok=True)
    load_history()
    threading.Thread(target=worker, daemon=True).start()
    port = CFG["app_port"]
    if CFG.get("remote_access") and CFG.get("remote_pin_hash"):
        BIND["host"] = "0.0.0.0"  # perangkat lain disaring di remote.kind(): hanya Tailscale + PIN
    srv = Server((BIND["host"], port), H)
    print("Seedance Studio: http://127.0.0.1:%d%s" % (port, " (akses HP via Tailscale aktif)" if BIND["host"] != "127.0.0.1" else ""),
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
