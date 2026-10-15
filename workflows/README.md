Taruh workflow custom di sini (format **API**: ComfyUI > Workflow > Export (API)).
Placeholder teks yang diganti otomatis: {{PROMPT}} {{ASPECT}} {{RESOLUTION}}
Placeholder angka (tulis sebagai string, jadi angka): "{{SEED}}" "{{DURATION}}" "{{WIDTH}}" "{{HEIGHT}}" "{{FRAMES}}"
- WIDTH/HEIGHT: dari Aspek + Resolusi (480p=480, 720p=768, 1080p=1088 sisi pendek), kelipatan 32.
- FRAMES: durasi x fps, dibulatkan naik ke grid frame model.
Kunci opsional "_studio" (dibuang sebelum dikirim ke ComfyUI):
  {"kind": "video|image|audio", "label": "nama di dropdown", "note": "catatan di UI", "max_short": 768,
   "max_duration": 15, "fps": 24, "frame_step": 17, "frame_offset": 5, "timeout": 7200,
   "models": [{"folder": "checkpoints", "file": "x.safetensors", "gb": 2, "url": "https://..."}]}
kind menentukan tahap: video -> 4 Production, image -> 3 Breakdown (gambar referensi/sketsa), audio -> 5 Editing (musik).
Workflow boleh menghasilkan video (SaveVideo), gambar (SaveImage) atau audio (SaveAudio).
Workflow muncul di dropdown "Workflow" pada UI.

Bawaan (lokal, gratis, tanpa kredit Comfy):
- minimax-h3-lokal.json — MiniMax H3 text-to-video + audio (8 step turbo LoRA).
  Model: diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors,
  text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors,
  vae/minimax_h3_video_vae_int8_convrot.safetensors, vae/minimax_h3_audio_vae_fp32.safetensors,
  loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors
  (https://huggingface.co/Comfy-Org/MiniMax-H3, LoRA: https://huggingface.co/lightx2v/Minimax-h3-Turbo)
- z-image-turbo-gambar.json — Z-Image Turbo gambar (karakter/lokasi/storyboard).
  Model: diffusion_models/z_image_turbo_int8_convrot.safetensors, text_encoders/qwen_3_4b_fp8_mixed.safetensors,
  vae/ae.safetensors (https://huggingface.co/Comfy-Org/z_image_turbo)
- ace-step-musik.json — ACE-Step musik instrumental (tags = prompt, durasi = panjang video).
  Model: checkpoints/ace_step_v1_3.5b.safetensors (https://huggingface.co/Comfy-Org/ACE-Step_ComfyUI_repackaged)
