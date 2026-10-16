"""Render final tahap Editing & Sound dengan ffmpeg (hanya pustaka standar Python).

Masukan (dict): clips [{path, start, end, text, tr}], transition "cut"|"fade"|"script", fade (dtk),
clip_audio (bool), clip_vol, music (path atau ""), music_vol, duck (bool: musik mengecil saat ada suara klip), subtitles (bool), out (path)."""
import json, os, shutil, subprocess, tempfile

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# transition_out dari script -> (filter xfade atau None = cut, durasi relatif terhadap `fade`)
SCRIPT_TR = {"dissolve": ("fade", 1.0), "fade to black": ("fadeblack", 1.2), "wipe": ("wipeleft", 0.8),
             "whip pan": ("slideleft", 0.5)}
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
    infos = []
    for c in clips:
        if job.get("cancelled") and job["cancelled"]():  # dibatalkan saat menyiapkan klip
            raise RuntimeError("Dibatalkan")
        infos.append(probe(c["path"]))
    W = infos[0]["width"] or 720
    H = infos[0]["height"] or 1280
    W, H = W // 2 * 2, H // 2 * 2
    base_fade = float(job.get("fade") or 0.5)
    mode = job.get("transition")
    # transisi tiap sambungan (antara klip i-1 dan i): (xfade, durasi); durasi 0 = cut
    joins = [("fade", base_fade) if mode == "fade" else
             ((SCRIPT_TR.get(str(clips[i - 1].get("tr") or "").lower(), (None, 0))[0],
               base_fade * SCRIPT_TR.get(str(clips[i - 1].get("tr") or "").lower(), (None, 0))[1]) if mode == "script"
              else (None, 0.0)) for i in range(1, len(clips))]
    joins = [(x, round(d, 3)) if x and d > 0 else (None, 0.0) for x, d in joins]
    fade = max([d for _, d in joins] + [0.0])
    end_fade = base_fade * 1.5 if mode == "script" and str(clips[-1].get("tr") or "").lower() == "fade to black" else 0.0
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
                   "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p,settb=AVTB[v%d]" % (i, a, b, W, H, W, H, i))
        if job.get("clip_audio", True) and info["audio"]:
            fil.append("[%d:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,aresample=48000,"
                       "aformat=sample_fmts=fltp:channel_layouts=stereo,volume=%.2f[a%d]"
                       % (i, a, b, float(job.get("clip_vol", 1)), i))
        else:
            fil.append("anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration=%.3f,"
                       "aformat=sample_fmts=fltp:channel_layouts=stereo[a%d]" % (d, i))
    n = len(clips)
    over = [0.0] + [d for _, d in joins]  # tumpang tindih di awal klip i
    starts, t = [], 0.0
    for i, d in enumerate(durs):
        t -= over[i]
        starts.append(t)
        t += d
    total = t
    if n == 1:
        fil.append("[v0]null[vc];[a0]anull[ac]")
    elif not fade:
        fil.append("".join("[v%d][a%d]" % (i, i) for i in range(n)) + "concat=n=%d:v=1:a=1[vc][ac]" % n)
    else:  # campuran cut & transisi: disambung satu per satu
        prev_v, prev_a = "v0", "a0"
        for i in range(1, n):
            ov, oa = ("vc", "ac") if i == n - 1 else ("vx%d" % i, "ax%d" % i)
            xf, d = joins[i - 1]
            if xf:
                fil.append("[%s][v%d]xfade=transition=%s:duration=%.3f:offset=%.3f[%s]" % (prev_v, i, xf, d, starts[i], ov))
                fil.append("[%s][a%d]acrossfade=d=%.3f[%s]" % (prev_a, i, d, oa))
            else:
                fil.append("[%s][%s][v%d][a%d]concat=n=2:v=1:a=1[%s][%s]" % (prev_v, prev_a, i, i, ov, oa))
            prev_v, prev_a = ov, oa
    if end_fade and total > end_fade * 2:  # scene terakhir "fade to black": gambar & suara memudar di akhir
        fil.append("[vc]fade=t=out:st=%.3f:d=%.3f[vcf];[ac]afade=t=out:st=%.3f:d=%.3f[acf]"
                   % (total - end_fade, end_fade, total - end_fade, end_fade))
    vfin, afin = ("vcf", "acf") if end_fade and total > end_fade * 2 else ("vc", "ac")
    vlast = vfin
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
            end = starts[i] + durs[i] - (over[i + 1] if i < n - 1 else 0)
            chain.append("drawtext=%stextfile=%s:fontsize=h*0.045:fontcolor=white:borderw=4:bordercolor=black@0.85:"
                         "line_spacing=8:x=(w-text_w)/2:y=h*0.80-text_h/2:enable='between(t,%.3f,%.3f)'"
                         % ("fontfile=%s:" % _fpath(font) if font else "", _fpath(tf), starts[i], end))
        if chain:
            fil.append("[%s]" % vfin + ",".join(chain) + "[vs]")
            vlast = "vs"
    alast = afin
    if job.get("music"):
        args += ["-stream_loop", "-1", "-i", job["music"]]
        m = n
        fo = max(0.0, total - 2.0)
        fil.append("[%d:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,atrim=duration=%.3f,"
                   "volume=%.2f,afade=t=in:d=0.5,afade=t=out:st=%.3f:d=2[m]" % (m, total, float(job.get("music_vol", 0.3)), fo))
        if job.get("duck", True) and job.get("clip_audio", True):  # hierarki mixing: ucapan di atas musik
            fil.append("[%s]asplit=2[ak][sc];[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=30:release=400[md]"
                       % afin)
            fil.append("[ak][md]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[am]")
        else:
            fil.append("[%s][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[am]" % afin)
        alast = "am"
    cmd = [shutil.which("ffmpeg") or "ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args + [
        "-filter_complex", ";".join(fil), "-map", "[%s]" % vlast, "-map", "[%s]" % alast,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", "%.3f" % total, job["out"]]
    return cmd, total


def render(job, progress=None, on_proc=None):
    """progress(pct) dipanggil selama ffmpeg berjalan (dari -progress: waktu yang sudah dirender / durasi total).
    on_proc(proses) dipanggil begitu ffmpeg mulai (supaya bisa dimatikan dari luar saat dibatalkan)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg tidak ditemukan di PATH.")
    tmp = tempfile.mkdtemp(prefix="studio-render-")
    try:
        cmd, total = build(job, tmp)
        cmd = cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]]
        with open(os.path.join(tmp, "ffmpeg-err.txt"), "w+b") as err:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, creationflags=NOWIN)
            if on_proc:
                on_proc(p)
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
