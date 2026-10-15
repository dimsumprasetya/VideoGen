@echo off
rem Buka firewall untuk akses Seedance Studio dari HP lewat Tailscale (sekali saja, minta izin admin).
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0izinkan-akses-hp.ps1\"'"
