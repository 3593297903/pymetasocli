"""Read only the approved source tree at the fixed commit; never copy runtime data."""
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
OLD = pathlib.Path('E:/metasocli')
COMMIT = 'f4153c31c63d63c4ead8b2a470dbc5d31ad04d3c'


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', '-c', 'safe.directory=E:/metasocli',
        '--no-optional-locks', '-C', str(OLD), *args])


def main() -> None:
    state = {'commit': git('rev-parse', 'HEAD').decode().strip(),
             'status': git('status', '--porcelain=v1').decode(),
             'remote': git('remote', '-v').decode()}
    baseline = ROOT / '.baseline'
    baseline.mkdir(exist_ok=True)
    paths = git('ls-tree', '-r', '-z', '--name-only', COMMIT).decode('utf-8').rstrip('\0').split('\0')
    allowed = ('src/', 'tests/', 'skills/', 'scripts/', 'examples/', 'docs/')
    tops = {'package.json', 'package-lock.json', 'tsconfig.json', 'vitest.config.mjs',
            'README.md', 'START_HERE.md', 'AGENTS.md'}
    entries = []
    for name in paths:
        if name not in tops and not name.startswith(allowed):
            continue
        blob = git('show', f'{COMMIT}:{name}')
        dest = baseline / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        entries.append({'source': name, 'commit': COMMIT,
            'sha256': hashlib.sha256(blob).hexdigest(),
            'target': '.baseline/' + name,
            'reason': 'Frozen reference for independent Python port and offline differential tests'})
    docs = ROOT / 'docs'
    docs.mkdir(exist_ok=True)
    (docs / 'SOURCE_MANIFEST.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
    (docs / 'BASELINE_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    handoff = ROOT / 'docs' / 'handoff'
    handoff.mkdir(exist_ok=True)
    for name in ('给新项目Codex的执行指令.txt', 'Python独立重建完整方案.md', 'semantic-probe.json'):
        (handoff / name).write_bytes((OLD / '.work/python-rebuild-plan-20261113' / name).read_bytes())
    print(json.dumps({'files': len(entries), 'baseline': state}, ensure_ascii=False))


if __name__ == '__main__':
    main()
