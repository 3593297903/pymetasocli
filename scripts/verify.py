"""Run the required offline gates and record each real command/exit status."""
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT/'.work/reports'
REPORTS.mkdir(parents=True, exist_ok=True)
commands = [
    ['uv', 'sync', '--locked', '--link-mode', 'copy'],
    ['uv', 'run', '--locked', '--no-sync', 'ruff', 'check', '.'],
    ['uv', 'run', '--locked', '--no-sync', 'mypy', 'src/metasocli_py'],
    ['uv', 'run', '--locked', '--no-sync', 'python', '-m', 'pytest', '--junitxml=.work/reports/pytest.xml'],
    ['uv', 'build'],
    [sys.executable, '-m', 'metasocli_py', '--version'],
    [sys.executable, '-m', 'metasocli_py', '--help'],
    ['uv', 'run', '--locked', '--no-sync', 'python', 'scripts/package_smoke.py'],
    ['uv', 'run', '--locked', '--no-sync', 'python', 'scripts/benchmark.py'],
]
report = {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
          'architecture': platform.machine(), 'commands': [], 'complete': False}
path = REPORTS/'verification.json'
for index, command in enumerate(commands):
    began = time.perf_counter()
    log = REPORTS/f'gate-{index+1:02}.log'
    print(json.dumps({'starting': command}), flush=True)
    with log.open('wb') as output:
        result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    report['commands'].append({'command': command, 'exitCode': result.returncode,
                              'seconds': time.perf_counter()-began, 'log': str(log.relative_to(ROOT))})
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['commands'][-1]), flush=True)
    if result.returncode:
        print(log.read_text(encoding='utf-8', errors='replace')[-16000:])
        sys.exit(result.returncode)
report['complete'] = True
path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'passed': True, 'report': str(path)}))
