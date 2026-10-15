"""Penulis ide/storyline/script lewat Ollama lokal (gratis). Hanya pustaka standar Python.
Ollama: https://ollama.com  (API http://127.0.0.1:11434)."""
import json, re, threading, urllib.error, urllib.request

RECOMMENDED = "qwen3:8b"   # ~5 GB, muat di VRAM 8 GB, bagus untuk bahasa Indonesia
ALTERNATIVES = ["qwen2.5:7b", "gemma3:4b", "llama3.2:3b"]  # cadangan bila qwen3 gagal (mis. Ollama versi lama)
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # Ollama lokal: jangan lewat proxy sistem
PROG = {"active": False, "task": "", "stage": "", "tokens": 0, "est": 0, "pct": 0}  # progres penulisan saat ini
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
        out = {"ok": True, "models": [m["name"] for m in tags.get("models", [])], "version": ""}
        try:
            with _req(base + "/api/version", timeout=3) as r:
                out["version"] = json.loads(r.read().decode()).get("version", "")
        except Exception:
            pass
        return out
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
        msg = str(e)
        hint = "Coba lewat Command Prompt: ollama pull %s" % model
        low = msg.lower()
        if "manifest" in low or "not found" in low or "does not exist" in low or "newer version" in low:
            hint = "Model tidak dikenal oleh Ollama ini: update Ollama dari ollama.com, atau pilih model lain (mis. qwen2.5:7b)."
        elif "space" in low or "disk" in low:
            hint = "Ruang disk tidak cukup (butuh ~6 GB di drive C:)."
        elif "timed out" in low or "connection" in low or "reset" in low or "eof" in low:
            hint = "Koneksi internet terputus. Klik Unduh lagi; Ollama melanjutkan dari posisi terakhir."
        PULL["error"] = "Unduh %s gagal: %s -> %s" % (model, msg[:200], hint)
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


def chat_json(base, model, system, user, schema, keep_alive="2m", timeout=900, est=600, task=""):
    """Minta jawaban JSON sesuai schema (structured output Ollama). Streaming supaya PROG berisi persen:
    token yang sudah ditulis / perkiraan panjang jawaban (est), maks 95% sampai selesai."""
    body = {"model": model, "stream": True, "format": schema, "keep_alive": keep_alive, "think": False,
            "options": {"temperature": 0.8, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    PROG.update(active=True, task=task, stage="Memuat model AI", tokens=0, est=max(50, int(est)), pct=0)
    try:
        return _chat(base, body, timeout)
    finally:
        PROG.update(active=False, pct=100, stage="Selesai")


def _chat(base, body, timeout):
    for attempt in (1, 2):
        try:
            text = []
            with _req(base + "/api/chat", body, timeout=timeout) as r:
                for line in r:
                    if not line.strip():
                        continue
                    ev = json.loads(line.decode())
                    if ev.get("error"):
                        raise RuntimeError("Ollama: " + str(ev["error"])[:300])
                    piece = (ev.get("message") or {}).get("content", "")
                    if piece:
                        text.append(piece)
                        PROG["tokens"] += 1
                        PROG.update(stage="Menulis", pct=min(95, int(100 * PROG["tokens"] / PROG["est"])))
                    if ev.get("done"):
                        break
            return _parse("".join(text))
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
    "type": "object", "required": ["duration", "location", "time", "action", "dialog", "onscreen_text", "visual"],
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
    return chat_json(base, model, SYSTEM, user, S_IDEAS, est=70 * n + 20, task="ideas")


def storyline(base, model, d):
    user = ("Develop this idea into a storyline for a %s-second vertical short video.\n"
            "Title: %s\nLogline: %s\nHook: %s\nOriginal prompt: %s\n%s\n"
            "Give: premise, 1-3 main characters (name + visual description: look, clothes, personality), "
            "setting, and beginning / middle / end (each 1-3 sentences). Write in %s."
            % (d.get("duration") or 30, d.get("title", ""), d.get("logline", ""), d.get("hook", ""),
               d.get("prompt", ""), _brief(d), d.get("lang") or "Bahasa Indonesia"))
    return chat_json(base, model, SYSTEM, user, S_STORY, est=380, task="storyline")


# Jenis suara: menentukan isi kolom dialog tiap scene. Kolom dialog WAJIB di schema; dengan structured output
# Ollama, kolom opsional hampir selalu dilewati model (dulu penyebab dialog/VO kosong).
VOICE = {
    "dialog": "Every scene MUST have spoken dialogue by the characters. Format each line as 'Name: line'.",
    "vo": "Every scene MUST have narrator voice-over. Format each line as 'VO: line'.",
    "mix": "Every scene MUST have at least one spoken line: character dialogue ('Name: line') and/or narrator "
           "voice-over ('VO: line'). Use VO to explain or teach, dialogue for character moments.",
    "none": "There is NO speech in this video (music and sound only): dialog must be an empty string.",
}
WPS = 2.3  # kata per detik ucapan santai; batas panjang dialog per scene


def _voice_rules(mode, lang):
    mode = mode if mode in VOICE else "mix"
    if mode == "none":
        return VOICE[mode]
    return (VOICE[mode] + " Separate several lines with a newline. Keep it speakable within the scene: at most "
            "about %.1f words per second of scene duration. Write the spoken words in %s; use the exact character "
            "names from the storyline." % (WPS, lang))


def script(base, model, d):
    total, max_scene = int(d.get("duration") or 30), int(d.get("max_scene") or 8)
    lang = d.get("lang") or "Bahasa Indonesia"
    n = max(1, round(total / max(3, min(max_scene, 6))))
    user = ("Turn this storyline into a shooting script for a %d-second vertical short video.\n\n%s\n\n"
            "Write about %d scenes; each scene 3-%d seconds; scene durations must add up to %d seconds.\n"
            "For each scene: duration (integer seconds), location, time (day/night/...), action (what happens), "
            "dialog (the spoken words, see rules), onscreen_text (short text shown on screen, or empty), and visual: "
            "ONE English prompt for an AI text-to-video model describing shot size, camera movement, subject, action, "
            "setting, lighting (no character names alone - describe how they look).\n"
            "DIALOG RULES: %s\n"
            "Write location, time, action, dialog and onscreen_text in %s."
            % (total, d.get("storyline", ""), n, max_scene, total, _voice_rules(d.get("voice"), lang), lang))
    res = chat_json(base, model, SYSTEM, user, S_SCRIPT, est=135 * n + 30, task="script")
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


S_BREAKDOWN = {"type": "object", "required": ["look", "characters", "locations", "props", "scenes"], "properties": {
    "look": {"type": "object", "required": ["style", "camera", "lighting", "palette"],
             "properties": {"style": {"type": "string"}, "camera": {"type": "string"},
                            "lighting": {"type": "string"}, "palette": {"type": "string"}}},
    "characters": {"type": "array", "items": {"type": "object", "required": ["name", "look", "wardrobe", "makeup"],
                   "properties": {"name": {"type": "string"}, "look": {"type": "string"},
                                  "wardrobe": {"type": "string"}, "makeup": {"type": "string"}}}},
    "locations": {"type": "array", "items": {"type": "object", "required": ["name", "description"],
                  "properties": {"name": {"type": "string"}, "description": {"type": "string"}}}},
    "props": {"type": "array", "items": {"type": "object", "required": ["name", "description"],
              "properties": {"name": {"type": "string"}, "description": {"type": "string"}}}},
    "scenes": {"type": "array", "items": {"type": "object", "required": ["scene", "characters", "location", "props", "shot", "camera"],
               "properties": {"scene": {"type": "integer"}, "characters": {"type": "array", "items": {"type": "string"}},
                              "location": {"type": "string"}, "props": {"type": "array", "items": {"type": "string"}},
                              "shot": {"type": "string"}, "camera": {"type": "string"}}}}}}


def breakdown(base, model, d):
    """Breakdown script: karakter (fisik, wardrobe, make-up), set/lokasi, properti, mood & style, dan isi tiap scene."""
    scenes = d.get("scenes") or []
    lines = ["Scene %d (%ss) | location: %s | time: %s | action: %s | dialog: %s" % (
        i + 1, s.get("duration", ""), s.get("location", ""), s.get("time", ""), s.get("action", ""), s.get("dialog", ""))
        for i, s in enumerate(scenes)]
    user = ("Make a production breakdown of this short-video script so every AI-generated shot stays visually consistent.\n\n"
            "STORYLINE:\n%s\n\nSCRIPT:\n%s\n\nVisual style wanted (may be empty): %s\n\n"
            "Return:\n- look: overall visual style (e.g. 3D animation / live action / anime), camera language, lighting, "
            "color palette.\n- characters: every character; look = fixed physical description (age, body, face, hair, "
            "skin/fur), wardrobe = clothes, makeup = make-up / hair styling / special effects (or 'none').\n"
            "- locations: every set/location with a reusable visual description.\n- props: important objects.\n"
            "- scenes: for EACH scene number 1-%d: character names present, location name, prop names, shot size "
            "(Wide, Medium, Close-up, Extreme close-up, Over-the-shoulder, POV, Top-down) and camera movement "
            "(Static, Pan, Tilt, Push-in, Pull-out, Tracking, Handheld, Orbit).\n"
            "Write ALL descriptions in English (they become AI video prompts); keep character and location names "
            "exactly as in the script."
            % (d.get("storyline", ""), "\n".join(lines), d.get("style", ""), len(scenes)))
    return chat_json(base, model, SYSTEM, user, S_BREAKDOWN, est=300 + 75 * len(scenes), task="breakdown")


S_DIALOG = {"type": "object", "required": ["lines"], "properties": {"lines": {"type": "array", "items": {
    "type": "object", "required": ["scene", "dialog"],
    "properties": {"scene": {"type": "integer"}, "dialog": {"type": "string"}}}}}}


def dialog(base, model, d):
    """Tulis (ulang) dialog / VO untuk scene yang sudah ada tanpa mengubah scene lainnya."""
    scenes = d.get("scenes") or []
    lang = d.get("lang") or "Bahasa Indonesia"
    lines = ["Scene %d (%ss): %s" % (i + 1, s.get("duration", ""), s.get("action", "")) for i, s in enumerate(scenes)]
    user = ("Write the spoken lines for this short vertical video, one entry for EACH scene 1-%d.\n\n"
            "STORYLINE:\n%s\n\nSCENES:\n%s\n\nDIALOG RULES: %s"
            % (len(scenes), d.get("storyline", ""), "\n".join(lines), _voice_rules(d.get("voice"), lang)))
    res = chat_json(base, model, SYSTEM, user, S_DIALOG, est=40 + 45 * len(scenes), task="dialog")
    out = [""] * len(scenes)
    for x in res.get("lines") or []:
        i = int(x.get("scene") or 0) - 1
        if 0 <= i < len(out):
            out[i] = str(x.get("dialog") or "").strip()
    return {"dialogs": out}

