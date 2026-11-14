"""Build-time one-way import of approved templates/helpers from the frozen baseline."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'src/metasocli_py'
records = []
for skill in ('metasocli-reference-images', 'metasoclitk'):
    source = ROOT / '.baseline/skills' / skill / 'references'
    for file in source.rglob('*'):
        if not file.is_file():
            continue
        dest = PACKAGE / 'resources' / ('reference-images' if skill.endswith('reference-images') else 'tk') / file.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = file.read_bytes()
        dest.write_bytes(data)
        records.append({'source': str(file.relative_to(ROOT)), 'destination': str(dest.relative_to(ROOT)),
                        'sourceSha256': hashlib.sha256(data).hexdigest(), 'destinationSha256': hashlib.sha256(data).hexdigest(),
                        'reason': 'Verbatim visual template or denoise resource; no runtime baseline dependency'})
for source_name, dest_name in [('validate_handoff.py', 'handoff.py'), ('append_asset_denoise.py', 'denoise.py')]:
    source = ROOT / '.baseline/skills/metasocli-reference-images/scripts' / source_name
    data = source.read_text(encoding='utf-8').replace('.metasocli/', '.metasocli-py/')
    if dest_name == 'denoise.py':
        start = data.index('# Reuse the existing')
        end = data.index('ValidationError = handoff.ValidationError')
        data = data[:start] + 'from . import handoff\nfrom importlib.resources import files\n' + data[end:]
        data = data.replace('POLICY_DIR = Path(__file__).resolve().parent.parent / "references/denoise"',
                            'POLICY_DIR = files("metasocli_py.resources").joinpath("reference-images/denoise")')
        data = data.replace('import importlib.util\n', '')
        data = data.replace('"metasoclitk"', '"metasoclitk-py"').replace('"metasocli-video-prompts"', '"metasocli-py-video-prompts"').replace('"metasocli-video-prompts-旁白"', '"metasocli-py-video-prompts-旁白"')
    else:
        a = data.index('    return hashlib.sha256(json.dumps(value, sort_keys=True')
        b = data.index('\n', a)
        data = data[:a] + '    from ..persistence.codec import digest\n    return digest(value)' + data[b:]
    dest = PACKAGE / 'media' / dest_name
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(data, encoding='utf-8', newline='\n')
    records.append({'source': str(source.relative_to(ROOT)), 'destination': str(dest.relative_to(ROOT)),
                    'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                    'destinationSha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
                    'reason': 'In-process module; new namespace, JCS and importlib.resources'})
(ROOT / 'docs/RESOURCE_MANIFEST.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Copied {len(records)} approved resource/helper files')
