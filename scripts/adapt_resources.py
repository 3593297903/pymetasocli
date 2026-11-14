"""Adapt copied documentation; preserve the three denoise byte streams exactly."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCE = ROOT/'src/metasocli_py/resources'
replacements = [
    ('metasocli-video-prompts-旁白', 'metasocli-py-video-prompts-旁白'),
    ('metasocli-video-prompts', 'metasocli-py-video-prompts'),
    ('metasocli-reference-images', 'metasocli-py-reference-images'),
    ('metasocli-prompt-engine', 'metasocli-py-prompt-engine'),
    ('metasoclitk', 'metasoclitk-py'),
    ('.metasocli/', '.metasocli-py/'), ('metasocli.yaml', 'metasocli-py.yaml'),
    ('node <package-root>/dist/cli/main.js', 'metasocli-py'),
]
for kind, skill in [('reference-images', 'metasocli-reference-images'), ('tk', 'metasoclitk')]:
    for source in (ROOT/'.baseline/skills'/skill/'references').rglob('*.md'):
        text = source.read_text(encoding='utf-8')
        for old, new in replacements:
            text = text.replace(old, new)
        text = text.replace('python -X utf8 -B <INSTALL_ROOT>/skills/metasocli-py-reference-images/scripts/append_asset_denoise.py',
                            'python -m metasocli_py.media.denoise')
        text = text.replace('[本地组装工具](../scripts/append_asset_denoise.py)', '`metasocli_py.media.denoise` 包内组装模块')
        text = text.replace('[ImportDraft](../../../docs/INPUT_FORMAT.md)', '严格 ImportDraft（包含 offsetEncoding=utf16）')
        text = text.replace('[图片执行授权与连续执行](../../../docs/IMAGE_EXECUTION_AUTHORIZATION.md)',
                            '本入口 SKILL.md 的授权规则：沿用当前用户已明确授权的供应商、范围和次数；宿主拒绝时报告并停止对应操作')
        text = text.replace('[实际用法](../../../docs/IMAGE_API_USAGE.md)', '[实际用法](image-workflow.md)')
        text = text.replace('[指定段提示词一次替换](../../../docs/PROMPT_REPLACEMENT.md)', '`prompts replace` 一次替换入口')
        text = text.replace('[video run](../../../docs/VIDEO_EXECUTE.md#固定视频入口)', '`video run`')
        if source.name == 'selected-local-image.md':
            start, end = text.index('输入为'), text.index('成功后只交付')
            text = text[:start] + '''核对故事根、原资产 ID 和用户选定文件后，一次调用：

```text
metasocli-py assets register --root <story> --id <original-id> --file <selected-file> --provenance user
```

有可信预期 SHA-256 时追加 `--expected-sha256 <hash>`。Core 读取实际字节、校验格式、计算 SHA、完成事务并返回 media.sha256。
检查返回的 assetId 与选图哈希；不单独提前复制文件、不写清单、不改配方。

''' + text[end:]
        if source.name == 'denoise-policy.md':
            text = text.replace('其他调用者保持原默认行为。', 'Python 新项目导入所有新人物/场景/道具配方时也会校验并幂等追加相同原文。')
            text = text.replace('只在 ', '显式批量 helper 在 ')
            text = text.replace('显式批量 helper 在 `metasoclitk-py`、`metasocli-py-video-prompts`、`metasocli-py-video-prompts-旁白` 三个入口以后', '六个 Python 新入口以后')
        if source.name == 'image-workflow.md':
            text = text.replace('以当前安装根定位 `dist/cli/main.js`。', '使用实际虚拟环境的 `python -m metasocli_py` 或安装后的 `metasocli-py`。')
            text = text.replace('append_asset_denoise.py', '`python -m metasocli_py.media.denoise`')
            text = text.replace('其他调用者不自动启用。', 'Python 新项目的所有新人物/场景/道具配方同样在哈希前追加，完整交接中的 generationPrompt 与 draft 必须一致。')
            text = text.replace('prepare 固定调用包内 Python 3.10+ 校验器、现有逐集导入和 all-ready 计划器。可用 `--python <本机可执行文件>`；缺 Python 明确失败，不假称校验完成，不自动安装。',
                                'prepare 在当前 Python 进程直接调用包内校验模块、逐集导入和 all-ready 计划器；无需额外解释器或 --python 参数。')
            text = text.replace('可明确传绝对输入路径，仍接受现有安全读取检查。', '仅 draft.source 可明确指向只读外部原文；其他批次输入使用故事内相对路径。')
            text = text.replace('profilePath=null 解析本安装原有配置并冻结', 'profilePath=null 使用本包严格默认 profile 并冻结')
            text = text.replace('prepare 返回准备ID、计划ID、已导入/剩余集、记录与计时路径及当前执行摘要。', 'prepare 返回 preparationId、planId、status 和 importedEpisodes；输入和进度保存在 .metasocli-py/image-preparations/<ID>/。')
            text = text.replace('失败摘要同时记录观察到的实际集。', '可从 state.json 核对已完成集，再用原 preparationId 恢复。')
            text = text.replace('collection-report.json', 'collections/<UUID>/report.json')
            text = text.replace('准备租约仅在本故事 `.metasocli-py/image-preparation.lock`', '准备租约位于本故事 `.metasocli-py/image-preparations/<ID>/preparation.lock`')
        dest = RESOURCE/kind/source.relative_to(ROOT/'.baseline/skills'/skill/'references')
        dest.write_text(text, encoding='utf-8')
records = json.loads((ROOT/'docs/RESOURCE_MANIFEST.json').read_text(encoding='utf-8'))
for row in records:
    source, dest = ROOT/row['source'], ROOT/row['destination']
    row['destinationSha256'] = hashlib.sha256(dest.read_bytes()).hexdigest()
    row['sourceSha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    row['reason'] = 'Verbatim denoise bytes' if dest.suffix == '.txt' else 'Python namespace, CLI/module references, JCS helper adaptation; visual guidance retained'
    if dest.suffix == '.txt':
        assert row['sourceSha256'] == row['destinationSha256']
(ROOT/'docs/RESOURCE_MANIFEST.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'resources': len(records), 'denoiseUnchanged': True}))
