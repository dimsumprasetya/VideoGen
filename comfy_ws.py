"""Progres job ComfyUI lewat websocket /ws (hanya pustaka standar Python).

ComfyUI mengirim event ke client_id yang mengirim prompt: execution_start, execution_cached, executing,
progress {value,max}, progress_state (versi baru), executed. Dari situ dihitung persentase berbobot:
sampler/node API berbobot besar, loader & decode kecil. Bila websocket gagal, job tetap jalan tanpa persen."""
import base64, json, os, socket, struct, threading, time
from urllib.parse import urlparse

HEAVY = ("KSampler", "SamplerCustom", "ByteDance", "Kling", "Veo", "Luma", "Minimax", "Runway", "Pika", "Moonvalley")


def _weight(ct):
    if any(h in ct for h in HEAVY):
        return 20.0
    if "Loader" in ct:
        return 2.0
    if "Decode" in ct or "Encode" in ct or "Save" in ct or "Create" in ct:
        return 1.5
    return 0.3


STAGES = [("Loader", "Memuat model"), ("Sampler", "Generate"), ("Decode", "Decode"), ("Save", "Menyimpan"),
          ("Create", "Menyusun video"), ("TextEncode", "Membaca prompt"), ("ByteDance", "Diproses di cloud")]


def _stage(ct):
    for k, v in STAGES:
        if k in ct:
            return v
    return "Memproses"


class Progress:
    """Hubungkan ke /ws sebelum prompt dikirim; isi job['progress'] = {pct, stage, step}."""

    def __init__(self, base, client_id, graph, job):
        self.base, self.cid, self.job = base, client_id, job
        self.ct = {k: v.get("class_type", "") for k, v in graph.items()}
        self.w = {k: _weight(c) for k, c in self.ct.items()}
        self.total = sum(self.w.values()) or 1.0
        self.done, self.cur, self.frac, self.step = set(), None, 0.0, ""
        self.pid = None
        self.sock = None
        self.ok = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self.ok.wait(3)  # tunggu sebentar supaya event awal tidak terlewat

    def close(self):
        s, self.sock = self.sock, None
        if s:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()

    # ---- websocket minimal (RFC 6455, klien)
    def _open(self):
        u = urlparse(self.base)
        host, port = u.hostname or "127.0.0.1", u.port or 80
        s = socket.create_connection((host, port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall(("GET /ws?clientId=%s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (self.cid, host, port, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                raise OSError("ws ditutup")
            buf += chunk
        head, rest = buf.split(b"\r\n\r\n", 1)
        if b" 101" not in head.split(b"\r\n", 1)[0]:
            raise OSError("ws ditolak")
        s.settimeout(None)
        return s, rest

    def _frames(self, s, buf):
        def read(n):
            nonlocal buf
            while len(buf) < n:
                chunk = s.recv(65536)
                if not chunk:
                    raise OSError("ws ditutup")
                buf += chunk
            out, buf = buf[:n], buf[n:]
            return out
        parts, op0 = [], 0
        while True:
            b1, b2 = read(2)
            fin, op, ln = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", read(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", read(8))[0]
            mask = read(4) if b2 & 0x80 else None
            data = read(ln)
            if mask:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if op == 9:  # ping -> pong (klien wajib memakai mask)
                m = os.urandom(4)
                s.sendall(bytes([0x8A, 0x80 | len(data)]) + m + bytes(c ^ m[i % 4] for i, c in enumerate(data)))
                continue
            if op == 8:
                return
            if op in (1, 2):
                op0, parts = op, [data]
            elif op == 0:
                parts.append(data)
            if fin and op in (0, 1, 2):
                yield op0, b"".join(parts)

    def _run(self):
        try:
            s, rest = self._open()
            self.sock = s
            self.ok.set()
            for op, data in self._frames(s, rest):
                if op == 1:
                    try:
                        self._on(json.loads(data.decode("utf-8", "replace")))
                    except ValueError:
                        pass
        except Exception:
            pass
        finally:
            self.ok.set()

    # ---- event ComfyUI -> persen
    def _on(self, msg):
        t, d = msg.get("type"), msg.get("data") or {}
        if self.pid and d.get("prompt_id") and d["prompt_id"] != self.pid:
            return
        if t == "execution_cached":
            self.done.update(str(n) for n in d.get("nodes") or [])
        elif t == "executing":
            node = d.get("node")
            if self.cur and self.cur != node:
                self.done.add(self.cur)
            self.cur, self.frac, self.step = (str(node) if node is not None else None), 0.0, ""
        elif t == "progress":
            mx = float(d.get("max") or 0)
            if mx:
                self.frac = min(1.0, float(d.get("value") or 0) / mx)
                self.step = "%d/%d" % (int(d.get("value") or 0), int(mx))
            if d.get("node") is not None:
                self.cur = str(d["node"])
        elif t == "progress_state":  # ComfyUI baru: status semua node sekaligus
            for nid, n in (d.get("nodes") or {}).items():
                if n.get("state") == "finished":
                    self.done.add(str(nid))
                elif n.get("state") == "running":
                    self.cur = str(nid)
                    mx = float(n.get("max") or 0)
                    if mx:
                        self.frac = min(1.0, float(n.get("value") or 0) / mx)
                        self.step = "%d/%d" % (int(n.get("value") or 0), int(mx))
        elif t == "executed" and d.get("node") is not None:
            self.done.add(str(d["node"]))
        else:
            return
        got = sum(self.w.get(n, 0) for n in self.done)
        if self.cur and self.cur not in self.done:
            got += self.w.get(self.cur, 0) * self.frac
        stage = _stage(self.ct.get(self.cur, "")) if self.cur else "Menyelesaikan"
        self.job["progress"] = {"pct": max(1, min(99, int(100 * got / self.total))), "stage": stage, "step": self.step}
