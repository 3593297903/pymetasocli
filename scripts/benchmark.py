"""20 fresh-process and 20 in-process same-fixture measurements, no business HTTP."""
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

from PIL import Image

from metasocli_py.application.assets import register_asset
from metasocli_py.application.story import import_story, initialize, load_story, replace_prompt
from metasocli_py.domain.text import normalize_text, utf16_length
from metasocli_py.video.planning import build_request, capture

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'.work'/('benchmark-'+uuid.uuid4().hex[:8])
BASE.mkdir(parents=True)
NODE = shutil.which('node')
if not NODE:
    raise RuntimeError('Baseline Node executable is required for comparison only')
ENV = {k: v for k, v in os.environ.items() if k not in ('METASO_API_KEY', 'METASOCLI_IMAGE_API_KEY', 'METASOCLI_PY_METASO_API_KEY', 'METASOCLI_PY_IMAGE_API_KEY', 'NODE_OPTIONS')}
ENV.update(METASO_RUNTIME_DIR=str(BASE/'node-runtime'), METASOCLI_PY_RUNTIME_DIR=str(BASE/'py-runtime'),
           METASOCLI_PY_CONFIG_DIR=str(BASE/'py-config'), PYTHONUTF8='1')


def run(command):
    started = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout, (time.perf_counter()-started)*1000


def stats(samples):
    ordered = sorted(samples)
    return {'iterations': len(samples), 'medianMs': statistics.median(samples), 'p95Ms': ordered[int(.95*len(ordered))-1], 'samplesMs': samples}


Image.new('RGB', (256, 256), 'red').save(BASE/'red.png')
Image.new('RGB', (256, 256), 'blue').save(BASE/'blue.png')
for index in range(2):
    (BASE/f'replace-{index}.txt').write_bytes(f'\ufeff完整替换稿{index}😀。\r\n'.encode('utf-8'))
bridge = str(ROOT/'scripts/baseline_bridge.mjs')
run([NODE, bridge, 'setup', str(BASE)])
python_root = BASE/'py-story'
initialize(python_root, 'Synthetic differential')
for episode in range(1, 7):
    source = BASE/f'source-{episode}.txt'
    text = normalize_text(source.read_bytes())
    cursor, segments = 0, []
    for i, prompt in enumerate(text.splitlines(keepends=True)):
        end = cursor+utf16_length(prompt)
        segments.append({'id': f's{i+1}', 'start': cursor, 'end': end, 'duration': 6.666,
                         'references': [{'assetId': 'hero', 'role': 'reference_image'}]})
        cursor = end
    import_story(python_root, {'episodeId': f'ep-{episode}', 'kind': 'video-prompts', 'source': str(source), 'offsetEncoding': 'utf16',
                              'segments': segments, 'recipes': [{'assetId': 'hero', 'kind': 'character', 'prompt': '完整人物配方'}]})
register_asset(python_root, 'hero', BASE/'red.png')
commands = {
    'node': [NODE, str(ROOT/'.baseline/dist/cli/main.js')],
    'python': [sys.executable, '-m', 'metasocli_py'],
}
results = {}
for name, prefix in commands.items():
    root = BASE/('node-story' if name == 'node' else 'py-story')
    rows = {'help': [], 'replacePrompt': [], 'replaceImage': []}
    for index in range(20):
        rows['help'].append(run([*prefix, '--help'])[1])
        rows['replacePrompt'].append(run([*prefix, 'prompts', 'replace', '--root', str(root), '--episode', 'ep-1', '--segment', 's1', '--file', str(BASE/f'replace-{index%2}.txt')])[1])
        rows['replaceImage'].append(run([*prefix, 'assets', 'register', '--root', str(root), '--id', 'hero', '--file', str(BASE/('red.png' if index%2 else 'blue.png'))])[1])
    results[name] = {'freshProcess': {key: stats(value) for key, value in rows.items()}}
results['node']['inProcessPrompt'] = stats(json.loads(run([NODE, bridge, 'hot', str(BASE)])[0]))
samples = []
for index in range(20):
    started = time.perf_counter()
    replace_prompt(python_root, 'ep-1', 's1', BASE/f'replace-{index%2}.txt')
    samples.append((time.perf_counter()-started)*1000)
results['python']['inProcessPrompt'] = stats(samples)
results['node']['inProcessImage'] = stats(json.loads(run([NODE, bridge, 'hot-image', str(BASE)])[0]))
samples = []
for index in range(20):
    started = time.perf_counter()
    register_asset(python_root, 'hero', BASE/('red.png' if index%2 else 'blue.png'))
    samples.append((time.perf_counter()-started)*1000)
results['python']['inProcessImage'] = stats(samples)
baseline = json.loads(run([NODE, bridge, 'payload', str(BASE)])[0])
story = load_story(python_root)
actual = [build_request(python_root, capture(story, ep['id'], seg['id'])) for ep in story['episodes'] for seg in ep['segments']]
assert baseline == actual, 'Actual request payload/text/media/reference order differs'
report = {'fixture': str(BASE), 'platform': platform.platform(), 'python': sys.version, 'pythonExecutable': sys.executable,
          'nodeExecutable': NODE, 'results': results, 'differential': {'requests': len(actual), 'identical': True,
          'compared': 'Full payload values, text/newlines, media Data URL bytes, ordered references; zero blanket exclusions'},
          'cacheNote': 'Fresh process is a cold interpreter start; OS filesystem cache is not purged. In-process uses warmed imports.'}
dest = ROOT/'.work/reports/performance.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'report': str(dest), 'differential': report['differential']}))
