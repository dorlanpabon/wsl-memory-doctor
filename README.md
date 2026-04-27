# wsl-memory-doctor

CLI local para diagnosticar `vmmem`/WSL, Docker Desktop y Podman desde Windows.

## Comandos

```powershell
python -m wsl_memory_doctor snapshot
python -m wsl_memory_doctor doctor
python -m wsl_memory_doctor history --window 24h
python -m wsl_memory_doctor export --format md
python -m wsl_memory_doctor drop-cache --distro Ubuntu-20.04
.\scripts\drop_wsl_cache.ps1 -Distro Ubuntu-20.04
.\scripts\set_wsl_memory_profile.ps1 -MemoryGB 8 -AutoMemoryReclaim dropCache
```
