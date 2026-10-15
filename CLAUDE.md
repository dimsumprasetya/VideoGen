# Seedance Shorts Studio

Web UI lokal (Python stdlib saja, tanpa dependensi) untuk membuat klip YouTube Shorts lewat ComfyUI + node API Seedance (ByteDance). Seedance berjalan di cloud lewat API node ComfyUI (butuh login akun Comfy + kredit), bukan di GPU lokal.

## File
- `app.py` — server HTTP (port 7860) + UI satu halaman (HTML ada di variabel `HTML`). Mengirim workflow API-format ke ComfyUI (`/prompt`), polling `/history`, mengunduh video ke `outputs/`, menggabungkan klip dengan ffmpeg.
- `studio.pyw` — supervisor latar belakang: menyalakan ComfyUI (deteksi otomatis atau `comfy_cmd`) + `app.py` tanpa jendela, restart otomatis, membuka jendela `--app` Edge/Chrome. Satu instance lewat lock socket di `app_port + 1`. Menulis `studio.pids` dan `studio.log`.
- `studio.vbs` — peluncur tersembunyi untuk `studio.pyw`. `stop.bat` — hentikan semua. `autostart-on.bat` / `autostart-off.bat` — tambah/hapus auto-start di folder Startup Windows. `run.bat` — jalan manual dengan console.
- `buat-shortcut.bat` — buat shortcut "Seedance Studio" di Desktop.
- `update.bat` — stop, `update.ps1`, nyalakan lagi (semua dalam satu baris karena .bat ikut ditimpa). `update.ps1 [branch]`: `git pull` bila ada `.git`, selain itu unduh ZIP GitHub (`archive/HEAD.zip` = branch default) dan salin di atas folder, kecuali `studio_config.json`/`api_key.txt` yang sudah ada. Folder pemilik bukan clone git (diunduh ZIP).
- API key akun Comfy (wajib untuk node API berbayar bila dipanggil lewat `/prompt` tanpa UI ComfyUI) dikirim di `extra_data.api_key_comfy_org`; disimpan di `api_key.txt` (gitignored) lewat UI, atau env `COMFY_API_KEY`.
- Model/aspek/resolusi dibaca dari `/object_info/ByteDanceTextToVideoNode`; input yang tidak dimiliki node disaring sebelum dikirim.
- `studio_config.json` — `comfy_cmd`, `comfy_cwd`, `comfy_ports` (8188 ComfyUI biasa, 8000 ComfyUI Desktop), `app_port`, dll.
- `comfy_detect.py` — deteksi/resolusi perintah menyalakan ComfyUI (Desktop .exe, folder manual, paket portable). UI menampilkan panel setup bila ComfyUI belum tersambung; pilihan disimpan ke `studio_config.json` dan supervisor membacanya ulang tiap 5 dtk.
- ComfyUI pemilik: portable di `C:\AI\ComfyUI_windows_portable` (python_embeded, port 8188, tanpa autentikasi), juga dipakai Luminar Studio (`C:\AI\relight-studio`, backend :8001). Start: `python_embeded\python.exe -s ComfyUI\main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch` dengan cwd folder portable; sudah diisi di `studio_config.json`. Antrean ComfyUI serial (VRAM 8 GB); node Seedance berjalan di cloud.
- Menumpang ComfyUI yang sudah jalan (mis. dinyalakan aplikasi lain): `comfy_url()` mencari port dari proses ComfyUI (PowerShell) bila 8188/8000 mati; panel setup juga menerima port. `cek-comfy.bat` menampilkan proses+port ComfyUI.
- `workflows/` — workflow custom (format **API**, bukan UI). Placeholder `{{PROMPT}} {{SEED}} {{DURATION}} {{ASPECT}} {{RESOLUTION}} {{IMAGE}}`, plus heuristik nama input (`prompt`, `seed`, `duration`, `aspect_ratio`, `resolution`, `generate_audio`, termasuk dynamic combo seperti `model.prompt`).
- Placeholder tambahan: `{{WIDTH}} {{HEIGHT}}` (dari aspek+resolusi, kelipatan 32) dan `{{FRAMES}}` (durasi x fps, grid frame model). Kunci opsional `_studio` (label, note, max_short, fps, frame_step, frame_offset, timeout) dibuang sebelum `/prompt`. Hasil boleh video atau gambar (SaveImage); gambar tidak bisa digabung.
- Workflow lokal gratis bawaan: `minimax-h3-lokal.json` (MiniMax H3 t2v+audio, open weights, ~40 GB model, turbo LoRA 8 step) dan `z-image-turbo-gambar.json` (Z-Image Turbo, gambar karakter/lokasi/storyboard). Diturunkan dari workflow UI pemilik (subgraph) secara manual; belum diuji dengan ComfyUI asli. MiniMax H3 di VRAM 8 GB sangat lambat/berisiko OOM.
- `_studio.models` (folder, file, gb, url): app cek keberadaan model lewat ComfyUI `GET /models/<folder>` sebelum kirim job, dan tombol "Unduh model yang kurang" mengunduh dari Hugging Face (urllib, `.part` + resume Range) ke folder dari `GET /internal/folder_paths` (cadangan `<comfy_cwd>/ComfyUI/models`). URL diambil dari catatan workflow pemilik, belum diverifikasi.
- Tab **Breakdown** (pra-produksi, meniru bagian Pre-Pro workflow pemilik): proyek di `projects/<nama>.json` (gitignored; `GET /api/projects`, `GET/POST /api/project`). Isi: script/beats, gaya visual, karakter, set/lokasi, panel storyboard (shot, kamera, lokasi, karakter, durasi). Tombol gambar memakai workflow gambar (default Z-Image) dengan template prompt character sheet / establishing shot / sketsa storyboard; job id disimpan di item, file diisi saat job selesai (sisi klien). "Pecah beats" membuat panel dari baris bernomor; "Ke Studio" mengisi prompt scene + durasi; tombol isi "Gaya & karakter" dari breakdown.
- UI punya kolom "Gaya & karakter" (localStorage) yang ditaruh di depan prompt scene; `params.scene` dipakai untuk label kartu.

## Catatan penting
- Node bawaan: `ByteDanceTextToVideoNode`, `ByteDanceImageToVideoNode`, `SaveVideo`. Model: seedance-1-0-pro-fast-251015, seedance-1-5-pro-251215 (durasi min 4 dtk, bisa audio), seedance-1-0-pro-250528, seedance-1-0-lite (t2v/i2v). Seedance 2.0 (`ByteDance2TextToVideoNode`, input dinamis) BELUM didukung workflow bawaan; lewat workflow custom. Belum diuji dengan ComfyUI + Seedance asli, jadi nama input node 2.0 perlu diverifikasi lewat `/object_info/ByteDance2TextToVideoNode`.
- Hanya pustaka standar Python. Jangan tambah dependensi tanpa alasan kuat.
- Target: Windows 10/11, Python di PATH, ffmpeg di PATH untuk fitur gabung.
- Uji cepat tanpa ComfyUI: jalankan server palsu di port 8188 yang membalas `/system_stats`, `/object_info/*`, `/history/*`, `/view`.

## Ide lanjutan
Seedance 2.0 sebagai workflow bawaan, penulis prompt/skrip otomatis per scene, subtitle/musik saat penggabungan, antrean dengan batas paralel, upload langsung ke YouTube.
