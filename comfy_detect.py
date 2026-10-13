"""Deteksi / resolusi perintah menyalakan ComfyUI. Dipakai app.py dan studio.pyw."""
import os, shutil, sys

HOME = os.path.expanduser("~")


def _py_in(d):
    for rel in (("python_embeded", "python.exe"), ("venv", "Scripts", "python.exe"),
                (".venv", "Scripts", "python.exe"), ("venv", "bin", "python"), (".venv", "bin", "python")):
        p = os.path.join(d, *rel)
        if os.path.exists(p):
            return p
    return shutil.which("python") or shutil.which("python3") or sys.executable


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
        extra = " --windows-standalone-build" if "python_embeded" in py else ""
        return '"%s" -s "%s"%s' % (py, os.path.join("ComfyUI", "main.py"), extra), path
    if os.path.isfile(os.path.join(path, "main.py")):           # instalasi manual
        return '"%s" main.py' % _py_in(path), path
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
    c += [os.path.join(local, "Programs", "ComfyUI"),
          os.path.join(local, "Programs", "@comfyorgcomfyui-electron"),
          os.path.join(HOME, "ComfyUI"), os.path.join(HOME, "Documents", "ComfyUI"),
          os.path.join(HOME, "Desktop", "ComfyUI"), os.path.join(HOME, "Downloads", "ComfyUI"),
          "C:\\ComfyUI", "D:\\ComfyUI"]
    for root in (HOME, os.path.join(HOME, "Desktop"), os.path.join(HOME, "Downloads"),
                 os.path.join(HOME, "Documents"), "C:\\", "D:\\"):
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
    return None, None
