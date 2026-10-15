"""Penulis ide/storyline/script lewat Ollama lokal (gratis). Hanya pustaka standar Python.
Ollama: https://ollama.com  (API http://127.0.0.1:11434)."""
import json, re, threading, urllib.error, urllib.request

RECOMMENDED = "qwen3:8b"   # ~5 GB, muat di VRAM 8 GB, bagus untuk bahasa Indonesia
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # Ollama lokal: jangan lewat proxy sistem
PULL = {"active": False, "model": "", "status": "", "done": 0, "total": 0, "error": ""}


def _req(url, data=None, timeout=10):
    req = urllib.request.Request(url, method="POST" if data is not None else "GET")
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    return _DIRECT.open(req, timeout=timeout)


def status(base):
    """{"ok": bool, "models": [nama]}"""
    try:
        with _req(base + "/api/tags", timeout=3) as r:
            tags = json.loads(r.read().decode())
        return {"ok": True, "models": [m["name"] for m in tags.get("models", [])]}
    except Exception:
        return {"ok": False, "models": []}


def pick_model(base, wanted=""):
    models = status(base)["models"]
    if wanted and wanted in models:
        return wanted
    for pref in (RECOMMENDED, "qwen3", "qwen2.5", "gemma3", "llama3"):
        for m in models:
            if m.startswith(pref):
                return m
    return models[0] if models else ""


def _pull(base, model):
    try:  # "name" untuk Ollama versi lama, "model" untuk versi baru
        with _req(base + "/api/pull", {"model": model, "name": model, "stream": True}, timeout=120) as r:
            for line in r:
                if not line.strip():
                    continue
                ev = json.loads(line.decode())
                if ev.get("error"):
                    raise RuntimeError(ev["error"])
                PULL.update(status=ev.get("status", ""), done=ev.get("completed", PULL["done"]),
                            total=ev.get("total", PULL["total"]))
    except Exception as e:
        PULL["error"] = ("Unduh model gagal: %s. Coba lewat Command Prompt: ollama pull %s" % (e, model))
    finally:
        PULL["active"] = False


def pull(base, model):
    if PULL["active"]:
        return
    # tandai aktif SEBELUM thread jalan, supaya UI langsung melihat unduhan berjalan
    PULL.update(active=True, model=model, status="memulai unduhan…", done=0, total=0, error="")
    threading.Thread(target=_pull, args=(base, model), daemon=True).start()


def _parse(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise RuntimeError("Jawaban LLM bukan JSON: " + text[:200])


def chat_json(base, model, system, user, schema, keep_alive="2m", timeout=900):
    """Minta jawaban JSON sesuai schema (structured output Ollama)."""
    body = {"model": model, "stream": False, "format": schema, "keep_alive": keep_alive, "think": False,
            "options": {"temperature": 0.8, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    for attempt in (1, 2):
        try:
            with _req(base + "/api/chat", body, timeout=timeout) as r:
                res = json.loads(r.read().decode())
            return _parse(res.get("message", {}).get("content", ""))
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if attempt == 1 and "think" in msg:   # model/versi Ollama tanpa dukungan opsi think
                body.pop("think")
                continue
            if attempt == 1 and "format" in msg:  # Ollama lama: format hanya "json"
                body["format"] = "json"
                continue
            raise RuntimeError("Ollama menolak: " + msg[:300])
        except urllib.error.URLError:
            raise RuntimeError("Ollama tidak menyala. Pasang dari ollama.com lalu jalankan.")
    raise RuntimeError("Ollama gagal menjawab.")


# ---------------------------------------------------------------- tugas penulisan
S_IDEAS = {"type": "object", "required": ["ideas"], "properties": {"ideas": {"type": "array", "items": {
    "type": "object", "required": ["title", "logline", "hook"],
    "properties": {"title": {"type": "string"}, "logline": {"type": "string"}, "hook": {"type": "string"}}}}}}

S_STORY = {"type": "object", "required": ["title", "premise", "characters", "beginning", "middle", "end"],
           "properties": {"title": {"type": "string"}, "premise": {"type": "string"},
                          "characters": {"type": "array", "items": {"type": "object", "required": ["name", "description"],
                                         "properties": {"name": {"type": "string"}, "description": {"type": "string"}}}},
                          "setting": {"type": "string"},
                          "beginning": {"type": "string"}, "middle": {"type": "string"}, "end": {"type": "string"}}}

S_SCRIPT = {"type": "object", "required": ["scenes"], "properties": {"scenes": {"type": "array", "items": {
    "type": "object", "required": ["duration", "location", "time", "action", "visual"],
    "properties": {"duration": {"type": "integer"}, "location": {"type": "string"}, "time": {"type": "string"},
                   "action": {"type": "string"}, "dialog": {"type": "string"}, "onscreen_text": {"type": "string"},
                   "visual": {"type": "string"}}}}}}

SYSTEM = ("You are a story developer and screenwriter for vertical short-form video (YouTube Shorts, 9:16). "
          "Stories must work visually in seconds, have a strong hook in the first 3 seconds, few characters, "
          "few locations and simple actions an AI video model can render. Always answer with JSON only.")


def _brief(d):
    parts = [("Audience", d.get("audience")), ("Genre", d.get("genre")), ("Tone", d.get("tone"))]
    return "\n".join("%s: %s" % (k, v) for k, v in parts if v)


def ideas(base, model, d):
    n = max(1, min(8, int(d.get("count") or 4)))
    user = ("Generate %d different story ideas for a short video based on this prompt:\n%s\n\n%s\n"
            "Write title, logline (1 sentence) and hook (what we see in the first 3 seconds) in %s."
            % (n, d.get("prompt", ""), _brief(d), d.get("lang") or "Bahasa Indonesia"))
    return chat_json(base, model, SYSTEM, user, S_IDEAS)


def storyline(base, model, d):
    user = ("Develop this idea into a storyline for a %s-second vertical short video.\n"
            "Title: %s\nLogline: %s\nHook: %s\nOriginal prompt: %s\n%s\n"
            "Give: premise, 1-3 main characters (name + visual description: look, clothes, personality), "
            "setting, and beginning / middle / end (each 1-3 sentences). Write in %s."
            % (d.get("duration") or 30, d.get("title", ""), d.get("logline", ""), d.get("hook", ""),
               d.get("prompt", ""), _brief(d), d.get("lang") or "Bahasa Indonesia"))
    return chat_json(base, model, SYSTEM, user, S_STORY)


def script(base, model, d):
    total, max_scene = int(d.get("duration") or 30), int(d.get("max_scene") or 8)
    n = max(1, round(total / max(3, min(max_scene, 6))))
    user = ("Turn this storyline into a shooting script for a %d-second vertical short video.\n\n%s\n\n"
            "Write about %d scenes; each scene 3-%d seconds; scene durations must add up to %d seconds.\n"
            "For each scene: duration (integer seconds), location, time (day/night/...), action (what happens), "
            "dialog or voice-over (empty if none), onscreen_text (empty if none), and visual: ONE English prompt "
            "for an AI text-to-video model describing shot size, camera movement, subject, action, setting, lighting "
            "(no character names alone - describe how they look). "
            "Write location, time, action, dialog and onscreen_text in %s."
            % (total, d.get("storyline", ""), n, max_scene, total, d.get("lang") or "Bahasa Indonesia"))
    res = chat_json(base, model, SYSTEM, user, S_SCRIPT)
    res["scenes"] = fit_durations(res.get("scenes") or [], total, max_scene)
    got = sum(x["duration"] for x in res["scenes"])
    if got != total:
        res["_warn"] = "Total %d dtk dari target %d dtk: tambah/hapus scene atau ubah durasi." % (got, total)
    return res


def fit_durations(scenes, total, max_scene, min_scene=2):
    """Skala durasi scene supaya jumlahnya = total, tiap scene di [min_scene, max_scene]."""
    if not scenes:
        return scenes
    raw = [max(1, int(s.get("duration") or 1)) for s in scenes]
    k = total / float(sum(raw))
    durs = [max(min_scene, min(max_scene, round(r * k))) for r in raw]
    for _ in range(100):  # koreksi pembulatan satu detik per langkah
        diff = total - sum(durs)
        if not diff:
            break
        step = 1 if diff > 0 else -1
        idx = [i for i, x in enumerate(durs) if min_scene <= x + step <= max_scene]
        if not idx:
            break
        i = min(idx, key=lambda j: durs[j]) if step > 0 else max(idx, key=lambda j: durs[j])
        durs[i] += step
    for s, x in zip(scenes, durs):
        s["duration"] = x
    return scenes
