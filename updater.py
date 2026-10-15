"""Pembaruan otomatis Seedance Studio dari GitHub (tanpa git). Hanya pustaka standar Python.

  python updater.py --now     cek & pasang pembaruan sekarang (dipakai update.bat)
  python updater.py --check   hanya cek, cetak sha lokal & terbaru

Sumber: branch `update_branch` di studio_config.json (default UPDATE_BRANCH di bawah).
Versi terpasang dicatat di version.txt (sha commit)."""
import io, json, os, shutil, sys, time, urllib.request, zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = "dimsumprasetya/VideoGen"
UPDATE_BRANCH = "claude/focused-lovelace-y9fz03"
VERSION_FILE = os.path.join(BASE, "version.txt")
# Milik pengguna: tidak pernah ditimpa / dihapus oleh pembaruan.
KEEP = {"studio_config.json", "api_key.txt", "python_path.txt", "version.txt", "studio.log", "studio.pids",
        "cek-ollama.txt"}
KEEP_DIRS = {"outputs", "projects", ".git"}
_DIRECT = urllib.request.build_opener()


def _cfg():
    try:
        with open(os.path.join(BASE, "studio_config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def branch():
    return _cfg().get("update_branch") or UPDATE_BRANCH


def local_version():
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def latest(br=None):
    """sha commit terbaru di branch, atau '' bila tidak bisa dicek (offline, rate limit)."""
    br = br or branch()
    req = urllib.request.Request("https://api.github.com/repos/%s/commits/%s" % (REPO, br),
                                 headers={"Accept": "application/vnd.github.sha", "User-Agent": "SeedanceStudio"})
    try:
        with _DIRECT.open(req, timeout=20) as r:
            sha = r.read().decode().strip()
        return sha if len(sha) == 40 else ""
    except Exception:
        return ""


def apply(sha, log=print):
    """Unduh ZIP commit `sha` dan salin di atas folder aplikasi. Return daftar file yang berubah."""
    url = "https://github.com/%s/archive/%s.zip" % (REPO, sha)
    log("update: unduh " + url)
    req = urllib.request.Request(url, headers={"User-Agent": "SeedanceStudio"})
    with _DIRECT.open(req, timeout=120) as r:
        data = r.read()
    changed = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        root = names[0].split("/", 1)[0] + "/"
        for n in names:
            rel = n[len(root):]
            if not rel:
                continue
            parts = rel.split("/")
            dst = os.path.join(BASE, *parts)
            if parts[0] in KEEP_DIRS:
                continue
            if len(parts) == 1 and parts[0] in KEEP and os.path.exists(dst):
                continue  # file milik pengguna; hanya dibuat bila belum ada (pemasangan baru)
            new = z.read(n)
            try:
                with open(dst, "rb") as f:
                    if f.read() == new:
                        continue
            except OSError:
                pass
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + ".new"
            with open(tmp, "wb") as f:
                f.write(new)
            os.replace(tmp, dst)
            changed.append(rel)
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(sha)
    log("update: %s terpasang, %d file berubah" % (sha[:7], len(changed)))
    return changed


def check_and_apply(log=print):
    """(sha_baru, file_berubah) bila ada pembaruan terpasang, selain itu (None, [])."""
    sha = latest()
    if not sha or sha == local_version():
        return None, []
    return sha, apply(sha, log)


if __name__ == "__main__":
    if "--check" in sys.argv:
        print("terpasang:", local_version() or "(belum tercatat)")
        print("terbaru  :", latest() or "(tidak bisa dicek)", "di branch", branch())
    else:
        sha, files = check_and_apply()
        if sha:
            print("Diperbarui ke %s (%d file)." % (sha[:7], len(files)))
        elif latest():
            print("Sudah versi terbaru.")
        else:
            print("Tidak bisa menghubungi GitHub. Cek internet.")
            sys.exit(1)
