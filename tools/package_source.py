"""Build a source-only ZIP using explicit inclusions; never bundle local credentials/data."""
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
files=[ROOT/name for name in (
    'README.md','DEMO.md','DESIGN_DECISIONS.md','VERIFICATION.md','pyproject.toml','uv.lock','.env.example','.gitignore',
    'setup.ps1','run.ps1','check.ps1',
    'frontend/package.json','frontend/package-lock.json','frontend/next.config.ts',
    'frontend/tsconfig.json','frontend/next-env.d.ts','frontend/AGENTS.md',
    'tools/check_transport.py','tools/live_voice_check.py','tools/check_supervisor_voice.py','tools/package_source.py','tools/configure_auth.py',
)]
for folder in ('backend','tests','frontend/src'):
    files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and
                 '__pycache__' not in p.parts and p.suffix in {'.py','.tsx','.ts','.css'})
destination=ROOT/'artifacts'/'effigov-voice-desk-source.zip'
destination.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(files)):
        if not path.exists():raise FileNotFoundError(path.name)
        archive.write(path,'effigov-voice-desk/'+path.relative_to(ROOT).as_posix())
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert all(Path(name).name not in {'.env','.env.local'} for name in archive.namelist())
print(f'Created {destination.name}: {len(files)} source files, {destination.stat().st_size:,} bytes')
