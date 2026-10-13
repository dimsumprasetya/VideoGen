#!/usr/bin/env python3
"""Seedance Shorts Studio: web UI lokal -> ComfyUI -> node API Seedance (Text-to-Video).
Hanya pustaka standar Python."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python_embeded tidak otomatis memuat folder script
import comfy_detect
import json, os, random, re, shutil, subprocess, sys, threading, time, uuid
import urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs")
WF = os.path.join(BASE, "workflows")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv")

DEFAULT_CFG = {"app_port": 7860, "comfy_ports": [8188, 8000], "poll_seconds": 3,
               "job_timeout_seconds": 1500}

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


def build_graph(p):
    """Workflow bawaan Text-to-Video Seedance (format API)."""
    inputs = {
        "model": p["model"], "prompt": p["prompt"], "resolution": p["resolution"],
        "aspect_ratio": p["aspect"], "duration": p["duration"], "seed": p["seed"],
        "camera_fixed": bool(p.get("camera_fixed")), "watermark": False,
    }
    if p.get("audio") and next((m for m in MODELS if m["id"] == p["model"]), {}).get("audio"):
        inputs["generate_audio"] = True
    return {
        "1": {"class_type": "ByteDanceTextToVideoNode", "inputs": inputs},
        "2": {"class_type": "SaveVideo", "inputs": {
            "video": ["1", 0], "filename_prefix": "video/seedance",
            "format": "auto", "codec": "auto"}},
    }


def custom_graph(name, p):
    path = os.path.join(WF, os.path.basename(name))
    with open(path, encoding="utf-8") as f:
        text = f.read()
    subs = {"{{PROMPT}}": p["prompt"], "{{ASPECT}}": p["aspect"], "{{RESOLUTION}}": p["resolution"]}
    for k, v in subs.items():
        text = text.replace('"%s"' % k, json.dumps(v))
        text = text.replace(k, json.dumps(v)[1:-1])
    text = text.replace('"{{SEED}}"', str(p["seed"])).replace('"{{DURATION}}"', str(p["duration"]))
    return json.loads(text)


def find_videos(outputs):
    found = []
    for node in outputs.values():
        for items in node.values():
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and str(it.get("filename", "")).lower().endswith(VIDEO_EXT):
                        found.append(it)
    return found


def run_job(job):
    try:
        base = comfy_url()
        if not base:
            raise RuntimeError("ComfyUI belum menyala. Tunggu sebentar atau cek studio.log.")
        p = job["params"]
        graph = custom_graph(p["workflow"], p) if p.get("workflow") else build_graph(p)
        job["status"] = "queued"
        try:
            res = http_json(base + "/prompt", {"prompt": graph, "client_id": job["id"]}, timeout=30)
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
            raise RuntimeError("ComfyUI menolak workflow: " + msg[:600])
        pid = res["prompt_id"]
        job["status"] = "running"
        deadline = time.time() + CFG["job_timeout_seconds"]
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
        raise RuntimeError("Timeout menunggu hasil dari Seedance (job dibatalkan).")
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


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
    prompt = str(d.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("Prompt kosong.")
    model = d.get("model") or MODELS[0]["id"]
    m = next((x for x in MODELS if x["id"] == model), None)
    dur = max(m["min_dur"] if m else 3, min(12, int(d.get("duration", 5))))
    seed = int(d.get("seed", -1))
    if seed < 0:
        seed = random.randint(0, 2**31 - 1)
    return {
        "prompt": prompt, "model": model, "duration": dur, "seed": seed,
        "aspect": d.get("aspect") if d.get("aspect") in ASPECTS else "9:16",
        "resolution": d.get("resolution") if d.get("resolution") in RESOLUTIONS else "720p",
        "audio": bool(d.get("audio")), "camera_fixed": bool(d.get("camera_fixed")),
        "workflow": os.path.basename(d["workflow"]) if d.get("workflow") else "",
    }


def merge(files):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg tidak ditemukan di PATH.")
    paths = [os.path.join(OUT, os.path.basename(f)) for f in files]
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
            wfs = sorted(f for f in os.listdir(WF) if f.endswith(".json")) if os.path.isdir(WF) else []
            self.send_json({"models": MODELS, "aspects": ASPECTS, "resolutions": RESOLUTIONS,
                            "workflows": wfs})
        elif u.path == "/api/status":
            log = ""
            try:
                with open(os.path.join(BASE, "studio.log"), encoding="utf-8", errors="replace") as f:
                    log = "\n".join(f.read().splitlines()[-4:])
            except OSError:
                pass
            self.send_json({"comfy": bool(comfy_url()), "ffmpeg": bool(shutil.which("ffmpeg")), "log": log})
        elif u.path == "/api/comfy/detect":
            cmd, cwd = comfy_detect.detect(CFG)
            self.send_json({"found": bool(cmd), "cmd": cmd or "", "cwd": cwd or ""})
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
        self.send_header("Content-Type", "video/mp4" if name.endswith(".mp4") else "application/octet-stream")
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
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px system-ui,sans-serif;height:100vh;display:grid;grid-template-columns:320px 1fr;grid-template-rows:1fr 150px}
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
</style></head><body>
<aside>
<h1>Seedance Studio <span id="st" class="chip">ComfyUI…</span></h1>
<div id="setup" style="display:none;background:#2a1d12;border:1px solid #5a3a1a;border-radius:8px;padding:10px;margin-bottom:8px">
<b>ComfyUI belum tersambung</b><div style="color:var(--mut);font-size:12px;margin:4px 0">Klik cari otomatis, atau tempel lokasi ComfyUI.exe / folder ComfyUI / port (mis. 8000) bila ComfyUI sudah jalan.</div>
<input id="cpath" placeholder="Lokasi ComfyUI.exe atau folder ComfyUI" style="width:100%;background:#0e0f12;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:8px;font:inherit">
<button id="cfind" style="margin-top:8px">Cari &amp; sambungkan</button><div id="cmsg" style="font-size:12px;margin-top:6px;color:var(--mut)"></div><pre id="clog" style="font-size:11px;color:var(--mut);white-space:pre-wrap;margin:6px 0 0"></pre></div>
<label>Prompt</label><textarea id="prompt" placeholder="Seekor kucing oranye berlari di atap kota saat senja, kamera mengikuti, sinematik"></textarea>
<label>Model</label><select id="model"></select>
<div class="row"><div><label>Aspek</label><select id="aspect"></select></div><div><label>Resolusi</label><select id="res"></select></div></div>
<label>Durasi: <b id="dv">5</b> detik</label><input type="range" id="dur" min="3" max="12" value="5">
<div class="row"><div><label>Seed (-1 = acak)</label><input type="number" id="seed" value="-1"></div></div>
<div class="chk" id="audw"><input type="checkbox" id="aud"><span>Generate audio</span></div>
<div class="chk"><input type="checkbox" id="cam"><span>Kamera tetap</span></div>
<label>Workflow</label><select id="wf"><option value="">Bawaan (Text-to-Video)</option></select>
<button id="go">Generate</button>
<button class="sec" id="merge" disabled>Gabung klip terpilih</button>
</aside>
<main><video id="v" controls loop style="display:none"></video><div id="msg">Tulis prompt lalu klik Generate. Hasil muncul di bawah.</div></main>
<footer id="list"></footer>
<script>
const $=id=>document.getElementById(id);let cfg,sel=new Set(),cur="";
const api=(p,b)=>fetch(p,b?{method:"POST",body:JSON.stringify(b)}:{}).then(r=>r.json());
function mdl(){return cfg.models.find(m=>m.id==$("model").value)}
function sync(){const m=mdl();$("dur").min=m.min_dur;if(+$("dur").value<m.min_dur)$("dur").value=m.min_dur;$("dv").textContent=$("dur").value;$("audw").style.display=m.audio?"flex":"none"}
async function init(){cfg=await api("/api/config");
$("model").innerHTML=cfg.models.map(m=>`<option value="${m.id}">${m.label}</option>`).join("");
$("aspect").innerHTML=cfg.aspects.map(a=>`<option>${a}</option>`).join("");
$("res").innerHTML=cfg.resolutions.map(a=>`<option ${a=="720p"?"selected":""}>${a}</option>`).join("");
cfg.workflows.forEach(w=>$("wf").insertAdjacentHTML("beforeend",`<option>${w}</option>`));
$("model").onchange=$("dur").oninput=sync;sync();poll();setInterval(poll,2000);status();setInterval(status,5000)}
async function status(){try{const s=await api("/api/status");$("st").textContent=s.comfy?"ComfyUI aktif":"ComfyUI mati";$("st").className="chip"+(s.comfy?" ok":"");$("setup").style.display=s.comfy?"none":"block";$("clog").textContent=s.log||"";$("merge").dataset.ff=s.ffmpeg?1:""}catch(e){}}
$("cfind").onclick=async()=>{$("cmsg").textContent="Mencari…";const r=await api("/api/comfy/save",{path:$("cpath").value});
$("cmsg").textContent=r.error?r.error:"Tersimpan. Menyalakan ComfyUI, tunggu sebentar…"};
$("go").onclick=async()=>{const r=await api("/api/generate",{prompt:$("prompt").value,model:$("model").value,aspect:$("aspect").value,resolution:$("res").value,duration:+$("dur").value,seed:+$("seed").value,audio:$("aud").checked,camera_fixed:$("cam").checked,workflow:$("wf").value});if(r.error)alert(r.error);else poll()};
function play(f){cur=f;$("v").src="/outputs/"+f;$("v").style.display="block";$("msg").style.display="none";$("v").play().catch(()=>{});render(last)}
let last=[];
function render(jobs){last=jobs;$("list").innerHTML=jobs.map(j=>{const d=j.status=="done";
return `<div class="card ${j.file&&j.file==cur?"sel":""}" onclick="${d?`play('${j.file}')`:`alert(${JSON.stringify(j.error||"Sedang diproses…").replace(/"/g,"&quot;")})`}">
${d?`<input type="checkbox" ${sel.has(j.file)?"checked":""} onclick="event.stopPropagation();tog('${j.file}')">`:""}
<span class="s ${j.status}">${{queued:"Antre…",running:"Memproses…",done:"Selesai",error:"Gagal"}[j.status]}</span>
<span class="p">${j.params.prompt.replace(/</g,"&lt;")}</span>
${d?`<span class="x" onclick="event.stopPropagation();del('${j.file}')">hapus</span>`:""}</div>`}).join("");
$("merge").disabled=sel.size<2}
function tog(f){sel.has(f)?sel.delete(f):sel.add(f);$("merge").disabled=sel.size<2}
async function del(f){if(!confirm("Hapus klip ini?"))return;await api("/api/delete",{file:f});sel.delete(f);poll()}
async function poll(){render(await api("/api/jobs"))}
$("merge").onclick=async()=>{$("merge").disabled=true;const order=last.filter(j=>sel.has(j.file)).reverse().map(j=>j.file);const r=await api("/api/merge",{files:order});if(r.error)alert(r.error);else{sel.clear();await poll();play(r.file)}};
init();
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
