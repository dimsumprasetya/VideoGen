"""Akses dari HP / laptop lain lewat Tailscale (jaringan pribadi). Hanya pustaka standar Python.

Aturan: koneksi dari PC sendiri (127.0.0.1) selalu boleh; koneksi lain hanya dari jaringan Tailscale
(`remote_nets`, default 100.64.0.0/10) dan wajib login PIN (cookie sesi 30 hari). Perangkat lain di Wi-Fi
atau internet ditolak walau port terbuka.

CLI (dipakai installer):  python remote.py --set-pin 123456 [--enable | --disable]"""
import hashlib, hmac, ipaddress, json, os, secrets, shutil, socket, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_FILE = os.path.join(BASE, "studio_config.json")
DEFAULT_NETS = ["100.64.0.0/10", "fd7a:115c:a1e0::/48"]  # alamat perangkat Tailscale
LOCAL_IPS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
COOKIE = "studio_auth"
MAX_AGE = 30 * 24 * 3600
FAILS = {}  # ip -> [jumlah gagal, terkunci sampai]
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def kind(ip, cfg):
    """'local' (PC sendiri), 'remote' (Tailscale, akses jarak jauh aktif) atau None (tolak)."""
    if ip in LOCAL_IPS:
        return "local"
    if not cfg.get("remote_access"):
        return None
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
        if addr.version == 6 and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
    except ValueError:
        return None
    for net in cfg.get("remote_nets") or DEFAULT_NETS:
        try:
            if addr in ipaddress.ip_network(net, strict=False):
                return "remote"
        except ValueError:
            pass
    return None


def host_ok(host, k):
    """Anti DNS-rebinding: nama host di header Host harus milik PC ini, bukan domain situs lain."""
    host = (host or "").strip().lower()
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    if host in LOCAL_HOSTS:
        return True
    if k != "remote":
        return False
    try:
        ipaddress.ip_address(host)
        return True                      # http://100.x.y.z:7860
    except ValueError:
        return "." not in host or host.endswith(".ts.net")  # MagicDNS: nama-pc / nama-pc.tailnet.ts.net


def _hash(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200000).hex()


def pin_fields(pin):
    """Field config untuk PIN baru (sesi lama otomatis tidak berlaku)."""
    pin = str(pin or "").strip()
    if len(pin) < 6:
        raise ValueError("PIN minimal 6 karakter.")
    salt = secrets.token_hex(16)
    return {"remote_pin_salt": salt, "remote_pin_hash": _hash(pin, salt), "remote_secret": secrets.token_hex(32)}


def check_pin(pin, cfg):
    if not cfg.get("remote_pin_hash"):
        return False
    return hmac.compare_digest(_hash(str(pin or "").strip(), cfg["remote_pin_salt"]), cfg["remote_pin_hash"])


def token(cfg):
    return hmac.new(bytes.fromhex(cfg["remote_secret"]), b"studio-session-v1", hashlib.sha256).hexdigest()


def authed(cookie_header, cfg):
    if not cfg.get("remote_secret"):
        return False
    want = token(cfg)
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE and hmac.compare_digest(v, want):
            return True
    return False


def cookie(cfg, clear=False):
    if clear:
        return "%s=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict" % COOKIE
    return "%s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict" % (COOKIE, token(cfg), MAX_AGE)


def locked(ip):
    n, until = FAILS.get(ip, (0, 0))
    return until > time.time()


def failed(ip):
    """Catat PIN salah; 5x salah -> terkunci 5 menit."""
    n, until = FAILS.get(ip, (0, 0))
    n += 1
    FAILS[ip] = [0, time.time() + 300] if n >= 5 else [n, 0]


def tailscale():
    """{installed, running, ips, name} dari CLI Tailscale; cadangan: alamat 100.x milik PC ini."""
    info = {"installed": False, "running": False, "ips": [], "name": ""}
    exe = shutil.which("tailscale") or next((p for p in (r"C:\Program Files\Tailscale\tailscale.exe",
                                                         r"C:\Program Files (x86)\Tailscale\tailscale.exe")
                                             if os.path.exists(p)), None)
    if exe:
        info["installed"] = True
        try:
            r = subprocess.run([exe, "status", "--json"], capture_output=True, timeout=8, creationflags=NOWIN)
            st = json.loads(r.stdout.decode(errors="replace") or "{}")
            me = st.get("Self") or {}
            info["running"] = st.get("BackendState") == "Running"
            info["ips"] = [ip for ip in me.get("TailscaleIPs") or [] if ":" not in ip]
            info["name"] = (me.get("DNSName") or "").rstrip(".")
        except Exception:
            pass
    if not info["ips"]:
        try:
            ips = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
            info["ips"] = sorted(ip for ip in ips if ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10"))
            info["running"] = info["running"] or bool(info["ips"])
        except Exception:
            pass
    return info


def _cli():
    try:
        with open(CFG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    args = sys.argv[1:]
    if "--set-pin" in args:
        cfg.update(pin_fields(args[args.index("--set-pin") + 1]))
    if "--enable" in args:
        if not cfg.get("remote_pin_hash"):
            sys.exit("Atur PIN dulu: python remote.py --set-pin 123456 --enable")
        cfg["remote_access"] = True
    if "--disable" in args:
        cfg["remote_access"] = False
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print("Akses jarak jauh:", "aktif" if cfg.get("remote_access") else "mati",
          "| PIN:", "sudah diatur" if cfg.get("remote_pin_hash") else "belum")


if __name__ == "__main__":
    _cli()
