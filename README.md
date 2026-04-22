# wsl-memory-doctor

CLI local para diagnosticar `vmmem`/WSL, Docker Desktop y Podman desde Windows.

## Comandos

```powershell
python -m wsl_memory_doctor snapshot
python -m wsl_memory_doctor doctor
python -m wsl_memory_doctor history --window 24h
python -m wsl_memory_doctor export --format md
```
