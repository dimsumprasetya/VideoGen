# Seedance Shorts Studio

Web UI lokal (Python stdlib saja, tanpa dependensi) untuk membuat klip YouTube Shorts lewat ComfyUI + node API Seedance (ByteDance). Seedance berjalan di cloud lewat API node ComfyUI (butuh login akun Comfy + kredit), bukan di GPU lokal.

## File
- `app.py` — server HTTP (port 7860) + UI satu halaman (HTML ada di variabel `HTML`). Mengirim workflow API-format ke ComfyUI (`/prompt`), polling `/history`, mengunduh video ke `outputs/`, menggabungkan klip dengan ffmpeg.
- `studio.pyw` — supervisor latar belakang: menyalakan ComfyUI (deteksi otomatis atau `comfy_cmd`) + `app.py` tanpa jendela, restart otomatis, membuka jendela `--app` Edge/Chrome. Satu instance lewat lock socket di `app_port + 1`. Menulis `studio.pids` dan `studio.log`.
- `studio.vbs` — peluncur tersembunyi untuk `studio.pyw`. `stop.bat` — hentikan semua. `autostart-on.bat` / `autostart-off.bat` — tambah/hapus auto-start di folder Startup Windows. `run.bat` — jalan manual dengan console.
- `buat-shortcut.bat` — buat shortcut "Seedance Studio" di Desktop.
- `studio_config.json` — `comfy_cmd`, `comfy_cwd`, `comfy_ports` (8188 ComfyUI biasa, 8000 ComfyUI Desktop), `app_port`, dll.
- `comfy_detect.py` — deteksi/resolusi perintah menyalakan ComfyUI (Desktop .exe, folder manual, paket portable). UI menampilkan panel setup bila ComfyUI belum tersambung; pilihan disimpan ke `studio_config.json` dan supervisor membacanya ulang tiap 5 dtk.
- Menumpang ComfyUI yang sudah jalan (mis. dinyalakan aplikasi lain): `comfy_url()` mencari port dari proses ComfyUI (PowerShell) bila 8188/8000 mati; panel setup juga menerima port. `cek-comfy.bat` menampilkan proses+port ComfyUI.
- `workflows/` — workflow custom (format **API**, bukan UI). Placeholder `{{PROMPT}} {{SEED}} {{DURATION}} {{ASPECT}} {{RESOLUTION}} {{IMAGE}}`, plus heuristik nama input (`prompt`, `seed`, `duration`, `aspect_ratio`, `resolution`, `generate_audio`, termasuk dynamic combo seperti `model.prompt`).

## Catatan penting
- Node bawaan: `ByteDanceTextToVideoNode`, `ByteDanceImageToVideoNode`, `SaveVideo`. Model: seedance-1-0-pro-fast-251015, seedance-1-5-pro-251215 (durasi min 4 dtk, bisa audio), seedance-1-0-pro-250528, seedance-1-0-lite (t2v/i2v). Seedance 2.0 (`ByteDance2TextToVideoNode`, input dinamis) BELUM didukung workflow bawaan; lewat workflow custom. Belum diuji dengan ComfyUI + Seedance asli, jadi nama input node 2.0 perlu diverifikasi lewat `/object_info/ByteDance2TextToVideoNode`.
- Hanya pustaka standar Python. Jangan tambah dependensi tanpa alasan kuat.
- Target: Windows 10/11, Python di PATH, ffmpeg di PATH untuk fitur gabung.
- Uji cepat tanpa ComfyUI: jalankan server palsu di port 8188 yang membalas `/system_stats`, `/object_info/*`, `/history/*`, `/view`.

## Ide lanjutan
Seedance 2.0 sebagai workflow bawaan, penulis prompt/skrip otomatis per scene, subtitle/musik saat penggabungan, antrean dengan batas paralel, upload langsung ke YouTube.
