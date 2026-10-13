"""Deteksi / resolusi perintah menyalakan ComfyUI. Dipakai app.py dan studio.pyw."""
import os, shutil, sys

HOME = os.path.expanduser("~")
FLAGS = " --listen 127.0.0.1 --port 8188 --disable-auto-launch"  # sama seperti peluncur Luminar


def _py_in(d):
    for base in (d, os.path.dirname(d.rstrip("\\/")), os.path.dirname(os.path.dirname(d.rstrip("\\/")))):
        p = _py_in1(base)
        if p:
            return p
    return shutil.which("python") or shutil.which("python3") or sys.executable


def _py_in1(d):
    for rel in (("python_embeded", "python.exe"), ("venv", "Scripts", "python.exe"),
                (".venv", "Scripts", "python.exe"), ("venv", "bin", "python"), (".venv", "bin", "python")):
        p = os.path.join(d, *rel)
        if os.path.exists(p):
            return p
    return None


def resolve(path):
    """Dari path yang dipilih user (ComfyUI.exe, folder ComfyUI, atau folder portable) -> (cmd, cwd) atau None."""
    path = (path or "").strip().strip('"')
    if not path:
        return None
    if os.path.isfile(path) and path.lower().endswith(".exe"):
        return '"%s"' % path, os.path.dirname(path)
    if not os.path.isdir(path):
        return None
    inner = os.path.join(path, "ComfyUI")
    if os.path.isfile(os.path.join(inner, "main.py")):          # paket portable
        py = _py_in(path)
        return '"%s" -s "%s"%s' % (py, os.path.join("ComfyUI", "main.py"), FLAGS), path
    if os.path.isfile(os.path.join(path, "main.py")):           # instalasi manual
        py = _py_in(path)
        parent = os.path.dirname(path.rstrip("\\/"))
        if "python_embeded" in py and os.path.dirname(os.path.dirname(py)) == parent:  # path = folder dalam paket portable
            return '"%s" -s "%s"%s' % (py, os.path.join("ComfyUI", "main.py"), FLAGS), parent
        return '"%s" main.py%s' % (py, FLAGS), path
    for exe in ("ComfyUI.exe",):
        p = os.path.join(path, exe)
        if os.path.isfile(p):
            return '"%s"' % p, path
    return None


def candidates(cfg=None):
    local = os.environ.get("LOCALAPPDATA", "")
    c = []
    if cfg and (cfg.get("comfy_cwd") or ""):
        c.append(cfg["comfy_cwd"])
    c += ["C:\\AI\\ComfyUI_windows_portable", "D:\\AI\\ComfyUI_windows_portable",
          os.path.join(local, "Programs", "ComfyUI"),
          os.path.join(local, "Programs", "@comfyorgcomfyui-electron"),
          os.path.join(HOME, "ComfyUI"), os.path.join(HOME, "Documents", "ComfyUI"),
          os.path.join(HOME, "Desktop", "ComfyUI"), os.path.join(HOME, "Downloads", "ComfyUI"),
          "C:\\ComfyUI", "D:\\ComfyUI"]
    for root in (HOME, os.path.join(HOME, "Desktop"), os.path.join(HOME, "Downloads"),
                 os.path.join(HOME, "Documents"), "C:\\", "D:\\", "C:\\AI", "D:\\AI"):
        try:
            for n in os.listdir(root):
                if n.lower().startswith("comfyui") and os.path.isdir(os.path.join(root, n)):
                    c.append(os.path.join(root, n))
        except OSError:
            pass
    return c


def detect(cfg=None):
    """(cmd, cwd) pertama yang valid, atau (None, None)."""
    if cfg and cfg.get("comfy_cmd"):
        return cfg["comfy_cmd"], (cfg.get("comfy_cwd") or None)
    for d in candidates(cfg):
        r = resolve(d)
        if r:
            return r
    for proc in running_comfy():  # ComfyUI sedang jalan (mis. dari aplikasi lain): tiru cara menyalakannya
        for start in (proc["exe"], proc["cmd"].split('"')[-1] if "main.py" in proc["cmd"] else ""):
            d = os.path.dirname(start) if start else ""
            for _ in range(4):
                r = resolve(d) if d else None
                if r:
                    return r
                nd = os.path.dirname(d)
                if nd == d:
                    break
                d = nd
    return None, None


_PS = (
    "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'comfy' -or $_.CommandLine -match 'comfy' };"
    "foreach ($x in $p) { $c = Get-NetTCPConnection -State Listen -OwningProcess $x.ProcessId -ErrorAction SilentlyContinue;"
    "foreach ($k in $c) { \"$($x.ProcessId)|$($k.LocalPort)|$($x.ExecutablePath)|$($x.CommandLine)\" } }"
)


def running_comfy():
    """Windows: proses ComfyUI yang sedang jalan (siapa pun yang menyalakan) -> [{pid, port, exe, cmd}]."""
    if os.name != "nt":
        return []
    import subprocess
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", _PS], capture_output=True,
                             text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        return []
    res = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4 and parts[1].isdigit():
            res.append({"pid": parts[0], "port": int(parts[1]), "exe": parts[2], "cmd": parts[3]})
    return res
