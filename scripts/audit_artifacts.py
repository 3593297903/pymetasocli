"""Audit distributable contents and publish nonrecursive artifact hashes."""
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path

from metasocli_py import __version__

ROOT = Path(__file__).resolve().parents[1]
files = [ROOT/'dist'/f'metasocli_py-{__version__}.whl', ROOT/'dist'/f'metasocli_py-{__version__}.tar.gz']
# Wheel filenames include Python/ABI/platform tags.
files[0] = next((ROOT/'dist').glob(f'metasocli_py-{__version__}-*.whl'))
records = []
for path in files:
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            assert sum(n.endswith('/SKILL.md') for n in names) == 6
            for source in (ROOT/'src/metasocli_py/resources').rglob('*'):
                if source.is_file() and '__pycache__' not in source.parts:
                    relative = source.relative_to(ROOT/'src').as_posix()
                    assert archive.read(relative) == source.read_bytes()
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
            assert any(n.endswith('/uv.lock') for n in names)
            assert any(n.endswith('/docs/ACCEPTANCE.md') for n in names)
            prefix = f'metasocli_py-{__version__}/'
            for relative in ('docs/ACCEPTANCE.md', 'pyproject.toml', 'uv.lock', 'README.md', 'src/metasocli_py/__init__.py'):
                member = archive.extractfile(prefix+relative)
                assert member is not None and member.read() == (ROOT/relative).read_bytes()
    assert not any(any(part in name.split('/') for part in ('.baseline', '.work', '.venv', '.git', 'node_modules', '__pycache__')) for name in names)
    records.append({'path': str(path), 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'archiveEntries': len(names)})
manifest = []
for folder in ('src', 'scripts', 'tests', 'skills'):
    for path in sorted((ROOT/folder).rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            manifest.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
for name in ('pyproject.toml', 'uv.lock', 'AGENTS.md'):
    manifest.append({'path': name, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest()})
result = {'version': __version__, 'newGitCommit': None, 'artifacts': records, 'implementationFiles': manifest,
          'baselineExcluded': True, 'nodeRuntimeRequired': False}
(ROOT/'docs/ARTIFACTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'version': __version__, 'artifacts': records, 'implementationFiles': len(manifest)}))
