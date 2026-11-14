"""Install the real wheel and locked runtime dependencies in a separate venv."""
import json
import os
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'.work'/('wheel-smoke-'+uuid.uuid4().hex[:8])
DEST.mkdir(parents=True)
wheel = sorted((ROOT/'dist').glob('*.whl'), key=lambda p: p.stat().st_mtime)[-1]
python = DEST/('venv/Scripts/python.exe' if os.name == 'nt' else 'venv/bin/python')
with zipfile.ZipFile(wheel) as package:
    names = package.namelist()
    assert not any('.baseline' in p or 'node_modules' in p or '/.work/' in p for p in names)
    assert sum(p.endswith('/SKILL.md') for p in names) == 6
commands = [
    ['uv', 'venv', str(DEST/'venv'), '--python', sys.executable],
    ['uv', 'export', '--locked', '--no-dev', '--no-editable', '--no-emit-project', '--output-file', str(DEST/'requirements.txt')],
    ['uv', 'pip', 'install', '--python', str(python), '--offline', '--requirements', str(DEST/'requirements.txt'), str(wheel)],
]
records = []
for command in commands:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    records.append({'command': command, 'exitCode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    if result.returncode:
        raise RuntimeError(result.stderr)
env = {k: v for k,v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME') and not ('KEY' in k.upper() or k.startswith('METASO'))}
env['PATH'] = str(python.parent) + os.pathsep + (str(Path(os.environ['SystemRoot'])/'System32') if os.name == 'nt' else '/nonexistent')
env['PYTHONUTF8'] = '1'
for arguments in [['-m', 'metasocli_py', '--version'], ['-m', 'metasocli_py', '--help'],
                  *[[str(ROOT/'scripts/wheel_child.py'), str(DEST/'stories'), entry] for entry in
                    ('metasocli-py-video-prompts', 'metasocli-py-video-prompts-旁白', 'metasoclitk-py')]]:
    command = [str(python), '-I', '-X', 'utf8', *arguments]
    result = subprocess.run(command, cwd=DEST, env=env, capture_output=True, text=True, encoding='utf-8', timeout=90)
    records.append({'command': command, 'exitCode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
path = ROOT/'.work/reports/package-smoke.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({'wheel': str(wheel), 'wheelBytes': wheel.stat().st_size, 'files': len(names), 'checks': records}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'passed': True, 'report': str(path), 'wheel': str(wheel)}))
