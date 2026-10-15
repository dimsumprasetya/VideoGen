"""Render final tahap Editing & Sound dengan ffmpeg (hanya pustaka standar Python).

Masukan (dict): clips [{path, start, end, text}], transition "cut"|"fade", fade (dtk),
clip_audio (bool), clip_vol, music (path atau ""), music_vol, subtitles (bool), out (path)."""
import json, os, shutil, subprocess, tempfile

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FONTS = [r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\meiryob.ttc", r"C:\Windows\Fonts\msgothic.ttc",
         r"C:\Windows\Fonts\arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]  # Yu Gothic: huruf Latin + Jepang


def probe(path):
    """{duration, width, height, audio}"""
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("ffprobe tidak ditemukan (ikut terpasang bersama ffmpeg).")
    r = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                        "-of", "json", path], capture_output=True, creationflags=NOWIN)
    if r.returncode:
        raise RuntimeError("Tidak bisa membaca %s" % os.path.basename(path))
    j = json.loads(r.stdout.decode() or "{}")
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
    return {"duration": float(j.get("format", {}).get("duration") or 0), "width": int(v.get("width") or 0),
            "height": int(v.get("height") or 0),
            "audio": any(s.get("codec_type") == "audio" for s in j.get("streams", []))}


def _fpath(p):
    """Path untuk opsi filter ffmpeg (Windows: C\\:/...)."""
    return "'" + p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'") + "'"


def build(job, tmpdir):
    """-> argumen ffmpeg, durasi total."""
    clips = job["clips"]
    if not clips:
        raise RuntimeError("Belum ada klip terpilih.")
    infos = [probe(c["path"]) for c in clips]
    W = infos[0]["width"] or 720
    H = infos[0]["height"] or 1280
    W, H = W // 2 * 2, H // 2 * 2
    fade = float(job.get("fade") or 0.5) if job.get("transition") == "fade" and len(clips) > 1 else 0.0
    args, fil, durs = [], [], []
    for i, (c, info) in enumerate(zip(clips, infos)):
        a = max(0.0, float(c.get("start") or 0))
        b = float(c.get("end") or 0) or info["duration"]
        b = min(b, info["duration"] or b)
        d = b - a
        if d <= max(0.2, fade):
            raise RuntimeError("Klip %d terlalu pendek setelah dipotong (%.1f dtk)." % (i + 1, d))
        durs.append(d)
        args += ["-i", c["path"]]
        fil.append("[%d:v]trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS,scale=%d:%d:force_original_aspect_ratio=decrease,"
                   "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p[v%d]" % (i, a, b, W, H, W, H, i))
        if job.get("clip_audio", True) and info["audio"]:
            fil.append("[%d:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,aresample=48000,"
                       "aformat=sample_fmts=fltp:channel_layouts=stereo,volume=%.2f[a%d]"
                       % (i, a, b, float(job.get("clip_vol", 1)), i))
        else:
            fil.append("anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration=%.3f,"
                       "aformat=sample_fmts=fltp:channel_layouts=stereo[a%d]" % (d, i))
    n = len(clips)
    starts, t = [], 0.0
    for i, d in enumerate(durs):
        starts.append(t)
        t += d - (fade if i < n - 1 else 0)
    total = t
    if n == 1:
        fil.append("[v0]null[vc];[a0]anull[ac]")
    elif fade:
        prev_v, prev_a = "v0", "a0"
        for i in range(1, n):
            ov, oa = ("vc", "ac") if i == n - 1 else ("vx%d" % i, "ax%d" % i)
            fil.append("[%s][v%d]xfade=transition=fade:duration=%.3f:offset=%.3f[%s]" % (prev_v, i, fade, starts[i], ov))
            fil.append("[%s][a%d]acrossfade=d=%.3f[%s]" % (prev_a, i, fade, oa))
            prev_v, prev_a = ov, oa
    else:
        fil.append("".join("[v%d][a%d]" % (i, i) for i in range(n)) + "concat=n=%d:v=1:a=1[vc][ac]" % n)
    vlast = "vc"
    if job.get("subtitles"):
        font = next((f for f in FONTS if os.path.exists(f)), "")
        chain = []
        for i, c in enumerate(clips):
            text = (c.get("text") or "").strip()
            if not text:
                continue
            tf = os.path.join(tmpdir, "sub%d.txt" % i)
            with open(tf, "w", encoding="utf-8") as f:
                f.write(text)
            end = starts[i] + durs[i] - (fade if i < n - 1 else 0)
            chain.append("drawtext=%stextfile=%s:fontsize=h*0.045:fontcolor=white:borderw=4:bordercolor=black@0.85:"
                         "line_spacing=8:x=(w-text_w)/2:y=h*0.80-text_h/2:enable='between(t,%.3f,%.3f)'"
                         % ("fontfile=%s:" % _fpath(font) if font else "", _fpath(tf), starts[i], end))
        if chain:
            fil.append("[vc]" + ",".join(chain) + "[vs]")
            vlast = "vs"
    alast = "ac"
    if job.get("music"):
        args += ["-stream_loop", "-1", "-i", job["music"]]
        m = n
        fo = max(0.0, total - 2.0)
        fil.append("[%d:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,atrim=duration=%.3f,"
                   "volume=%.2f,afade=t=in:d=0.5,afade=t=out:st=%.3f:d=2[m]" % (m, total, float(job.get("music_vol", 0.3)), fo))
        fil.append("[ac][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[am]")
        alast = "am"
    cmd = [shutil.which("ffmpeg") or "ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args + [
        "-filter_complex", ";".join(fil), "-map", "[%s]" % vlast, "-map", "[%s]" % alast,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", "%.3f" % total, job["out"]]
    return cmd, total


def render(job, progress=None):
    """progress(pct) dipanggil selama ffmpeg berjalan (dari -progress: waktu yang sudah dirender / durasi total)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg tidak ditemukan di PATH.")
    tmp = tempfile.mkdtemp(prefix="studio-render-")
    try:
        cmd, total = build(job, tmp)
        cmd = cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]]
        with open(os.path.join(tmp, "ffmpeg-err.txt"), "w+b") as err:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, creationflags=NOWIN)
            for line in p.stdout:
                key, _, val = line.decode(errors="replace").strip().partition("=")
                if key in ("out_time_us", "out_time_ms") and progress and total:
                    try:
                        progress(max(0, min(99, int(100 * int(val) / 1e6 / total))))
                    except ValueError:
                        pass  # "N/A" di awal
            p.wait()
            if p.returncode:
                err.seek(0)
                raise RuntimeError("ffmpeg gagal: " + err.read().decode(errors="replace")[-600:])
        return total
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
