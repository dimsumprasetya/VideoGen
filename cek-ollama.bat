@echo off
rem Cek Ollama untuk Seedance Studio. Hasil cek disimpan ke cek-ollama.txt
cd /d "%~dp0"
(
echo === where ollama
where ollama
echo.
echo === ollama --version
ollama --version
echo.
echo === API Ollama 127.0.0.1:11434
curl -s -m 5 http://127.0.0.1:11434/api/version
echo.
curl -s -m 5 http://127.0.0.1:11434/api/tags
echo.
echo.
echo === Status dari Seedance Studio
curl -s -m 10 http://127.0.0.1:7860/api/llm/status
echo.
echo.
echo === Ruang disk C: ^(GB^)
powershell -NoProfile -Command "$d=Get-PSDrive C; 'terpakai {0:N1} GB, sisa {1:N1} GB' -f ($d.Used/1GB),($d.Free/1GB)"
) > cek-ollama.txt 2>&1
type cek-ollama.txt
echo.
echo === Mencoba unduh qwen3:8b langsung (tekan Ctrl+C untuk batal)
ollama pull qwen3:8b
echo.
echo Kirim ke Claude: isi cek-ollama.txt dan pesan terakhir di atas (screenshot jendela ini juga boleh).
pause
