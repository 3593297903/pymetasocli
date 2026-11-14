"""Generate reviewable source/test inventory, CLI help, schemas and error locations."""
import argparse
import ast
import json
from pathlib import Path

from metasocli_py.cli import parser
from metasocli_py.contracts.story import ImportDraft, Manifest
from metasocli_py.images.contracts import Profile

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT/'docs'
GROUPS = [
    (['asset-replacement', 'prompt-replacement', 'prompt-replacement-cli', 'story', 'duration', 'planning', 'narration'],
     ['test_local_story.py', 'test_acceptance_edges.py', 'test_foundation.py'],
     '原ID、6集11段、并发替换、原文/旁白UTF-16、计划失效；scripts/benchmark.py另做11条完整payload差分'),
    (['audio'], ['test_foundation.py', 'test_retry_ir_edges.py'], 'PCM/float WAV、VBR/ID3/Xing、错误元数据；ffmpeg合成4秒音视频实际解码'),
    (['canonical'], ['test_foundation.py'], '新JCS向量及缺失/null/false/0；不沿用旧localeCompare结构化哈希'),
    (['cli', 'client', 'submit', 'inline-context-ir'], ['test_video_http.py', 'test_process_boundaries.py', 'test_acceptance_edges.py'],
     '实际CLI、请求契约、inline=true、提交意图/回执；scripts/package_smoke.py另验独立wheel'),
    (['credentials'], ['test_credentials_skills.py'], '独立变量/假token/真DPAPI/短时本机表单；旧凭据不读取'),
    (['storage', 'storage-concurrency', 'storage-path-retry'], ['test_process_boundaries.py', 'test_network_atomic.py'],
     '真实Windows进程、事务崩溃、稳定OS锁、原子替换/身份变化；不复制Node可删除PID锁机制'),
    (['capacity-auto-release', 'capacity-dispatch', 'coordinator-boundaries', 'cross-project-ack', 'project-isolation-video'],
     ['test_capacity_ir.py', 'test_video_http.py', 'test_network_atomic.py', 'test_revision_boundaries.py'],
     'R3观察水位/终态/迟到ID/5held/来源证据、公平票据与项目限额；不迁移旧ack格式'),
    (['context-ir', 'context-ir-contract', 'context-ir-recovery', 'context-ir-reuse'],
     ['test_capacity_ir.py', 'test_retry_ir_edges.py'], '显式独立请求/恢复/审核/派生、等价准备重新绑定、旧派生review不可覆盖'),
    (['context-ir-legacy', 'project-isolation-compat'], ['test_acceptance_edges.py', 'test_retry_ir_edges.py'],
     '旧活跃任务不接管；合成静态内容导入；新IR记录自有严格身份，非旧记录直接兼容'),
    (['image-api', 'image-api-http', 'image-transport'], ['test_image_http.py', 'test_image_recovery.py', 'test_network_atomic.py'],
     '真HTTP JSON/multipart/池/总deadline/代理/URL与b64；200独立请求与实际字节归属'),
    (['image-2k-landscape', 'image-api-boundaries', 'image-denoise-prompt'],
     ['test_revision_boundaries.py', 'test_foundation.py', 'test_image_recovery.py'],
     '显式规格、严格profile、去噪原文/类型/幂等；保留模板资源'),
    (['image-api-restart', 'image-existing-unknown-ack', 'image-retry-ancestry', 'image-manual-selection-recovery'],
     ['test_image_recovery.py', 'test_acceptance_edges.py', 'test_revision_boundaries.py', 'test_process_boundaries.py'],
     '完整回执恢复、无自动POST、DAG/人工选择保护、一次后继、丢job证据拒绝；旧ack参数不兼容'),
    (['image-preparation-restart', 'image-workflow-recovery', 'image-workflow-review', 'image-workflow'],
     ['test_image_recovery.py', 'test_revision_boundaries.py'],
     '严格完整交接/投影校验、持久准备/计划意图、本地collect与index/readiness；同进程校验器'),
    (['project-isolation-images'], ['test_image_recovery.py', 'test_revision_boundaries.py', 'test_acceptance_edges.py'],
     '跨故事未知隔离、共享已知配额、同故事提交lease、失败不取消其他回包'),
    (['batch-known-failure-retry', 'video-unknown-retry', 'video-recovered-failure-retry', 'video-execute-regressions', 'video-recovery-boundaries'],
     ['test_video_http.py', 'test_retry_ir_edges.py', 'test_revision_boundaries.py', 'test_process_boundaries.py'],
     '一次稳定新尝试、A/B/C、授权范围、损坏成片同伴恢复、原ID不重发；新记录不接受旧trace格式'),
    (['recovery', 'video-batch-faults', 'video-batch', 'video-execute', 'video-run', 'video-run-cli'],
     ['test_video_http.py', 'test_capacity_ir.py', 'test_acceptance_edges.py', 'test_process_boundaries.py', 'test_revision_boundaries.py'],
     '8段持续补位、慢下载分离、全/部分复用、单次CLI、七类杀进程checkpoint、原请求恢复'),
]
mapping = {}
for names, tests, note in GROUPS:
    for name in names:
        mapping[name+'.test.ts'] = (tests, note)
baseline_tests = sorted((ROOT/'.baseline/tests').glob('*.test.ts'))
assert set(mapping) == {p.name for p in baseline_tests}
lines = ['# 源测试场景映射', '',
    f'实际基线为 {len(baseline_tests)} 个 TypeScript 测试文件，另有 reference_image_skill_test.py，共 {len(baseline_tests)+1} 个测试文件。全部已读。', '',
    '映射按业务场景及验证方法建立；没有声称每个旧断言都机械移植。旧运行格式、Node锁实现和自动POST退避按本次新协议明确替换，见 FEATURE_MATRIX.md。通过/失败/跳过以最终pytest XML为准。', '',
    '| 固定基线测试 | Python证据 | 对照场景/明确变化 |', '|---|---|---|']
for path in baseline_tests:
    targets, note = mapping[path.name]
    for target in targets:
        assert (ROOT/'tests'/target).is_file()
    links = '、'.join(f'[{n}](../tests/{n})' for n in targets)
    lines.append(f'| `{path.name}` | {links} | {note} |')
lines.append('| `reference_image_skill_test.py` | [test_foundation.py](../tests/test_foundation.py)、[test_credentials_skills.py](../tests/test_credentials_skills.py)、[test_image_recovery.py](../tests/test_image_recovery.py)、[package_smoke.py](../scripts/package_smoke.py) | 单向适配helper、去噪哈希、完整交接、真实回执、六Skill资源/三入口临时安装/独立wheel；不运行旧Node生产代码 |')
lines += ['', '## Python实际测试函数清单', '', '参数化项及 Hypothesis 样本数不等于独立业务场景数。', '']
inventory = []
for path in sorted((ROOT/'tests').glob('test_*.py')):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_')]
    inventory.append({'file': path.relative_to(ROOT).as_posix(), 'tests': names})
    lines += [f'### {path.name}', '', *[f'- `{n}`' for n in names], '']
(DOCS/'SOURCE_TEST_MAP.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
(DOCS/'TEST_INVENTORY.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

errors: dict[str, set[str]] = {}
for path in sorted((ROOT/'src/metasocli_py').rglob('*.py')):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('AppError', 'ProviderError') and node.args:
            code = node.args[0]
            if isinstance(code, ast.Constant) and isinstance(code.value, str):
                errors.setdefault(code.value, set()).add(f'{path.relative_to(ROOT).as_posix()}:{node.lineno}')
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == 'code' and isinstance(value, ast.Constant) and isinstance(value.value, str):
                    errors.setdefault(value.value, set()).add(f'{path.relative_to(ROOT).as_posix()}:{node.lineno}')
lines = ['# 错误码索引', '', '由当前源码的字面量错误码生成；动态包装的底层I/O错误归入 LOCAL_INPUT_OR_IO/LOCAL_IO。错误不会回显 Key、原始响应、完整签名URL或Pydantic输入。', '',
         'CLI：0为当前操作成功，1为输入/身份/本地错误，2为部分交付/待恢复/停止。部分结果内逐项error应结合状态读取，不能把unknown当失败。', '', '| 错误码 | 实现位置 |', '|---|---|']
lines += [f'| `{code}` | '+', '.join(f'`{p}`' for p in sorted(paths))+' |' for code, paths in sorted(errors.items())]
(DOCS/'ERROR_CODES.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')

lines = ['# 当前 CLI 帮助', '', '从本版本实际 argparse 解析器生成；以新参数为准，不兼容的旧参数见 FEATURE_MATRIX.md。', '']
def visit(command: argparse.ArgumentParser, prefix: str):
    lines.extend([f'## {prefix}', '', '```text', command.format_help().rstrip(), '```', ''])
    for action in command._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                visit(sub, prefix+' '+name)
visit(parser(), 'metasocli-py')
(DOCS/'CLI_REFERENCE.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
(DOCS/'schemas').mkdir(exist_ok=True)
for name, model in [('import-draft', ImportDraft), ('manifest', Manifest), ('image-profile', Profile)]:
    (DOCS/'schemas'/f'{name}.json').write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'baselineTestFiles': len(baseline_tests)+1, 'pythonTestFunctions': sum(len(r['tests']) for r in inventory), 'errorCodes': len(errors)}))
