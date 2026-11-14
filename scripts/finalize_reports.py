"""Publish only completed, actually recorded offline acceptance results."""
import datetime
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from metasocli_py import __version__

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'.work/reports'
DOCS = ROOT/'docs'
DEST = DOCS/'reports'
DEST.mkdir(exist_ok=True)
verification = json.loads((WORK/'verification.json').read_text(encoding='utf-8'))
assert verification['complete'] and len(verification['commands']) == 9
assert all(row['exitCode'] == 0 for row in verification['commands'])
assert __version__ in (WORK/'gate-06.log').read_text(encoding='utf-8')
suites = ET.parse(WORK/'pytest.xml').getroot().findall('testsuite')
counts = {key: sum(int(s.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
assert counts['tests'] > 0 and not any(counts[k] for k in ('failures', 'errors', 'skipped'))
package = json.loads((WORK/'package-smoke.json').read_text(encoding='utf-8'))
assert all(row['exitCode'] == 0 for row in package['checks'])
performance = json.loads((WORK/'performance.json').read_text(encoding='utf-8'))
assert performance['differential']['identical'] and performance['differential']['requests'] == 11

def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=E:/metasocli', '--no-optional-locks', '-C', 'E:/metasocli', *args], text=True, encoding='utf-8').strip()
before = json.loads((DOCS/'BASELINE_STATE.json').read_text(encoding='utf-8'))
after = {'commit': git('rev-parse', 'HEAD'), 'status': git('status', '--porcelain=v1'), 'remote': git('remote', '-v')}
assert after['commit'] == before['commit'] and after['status'] == before['status'].strip()
assert after['remote'] == before['remote'].strip()
source = json.loads((DOCS/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
resources = json.loads((DOCS/'RESOURCE_MANIFEST.json').read_text(encoding='utf-8'))
for row in resources:
    assert hashlib.sha256((ROOT/row['destination']).read_bytes()).hexdigest() == row['destinationSha256']
for path in WORK.iterdir():
    if path.is_file() and path.suffix in ('.json', '.log', '.xml'):
        shutil.copy2(path, DEST/path.name)
stamp = datetime.datetime.now(datetime.UTC).isoformat()
(DEST/'old-project-final.json').write_text(json.dumps({'checkedAt': stamp, 'before': before, 'after': after,
    'unchangedTrackedWorktree': True, 'businessDataAccessed': False}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

image = json.loads((WORK/'image-200.json').read_text(encoding='utf-8'))
video = json.loads((WORK/'video-eight.json').read_text(encoding='utf-8'))
lines = ['# 性能与资源实测', '', f'版本 {__version__}；记录时间 {stamp}。', '',
    '同机、同一6集11段合成输入；旧Node仅在 .baseline 构建。每个条目20次，P95为排序后第19项；冷启动指新解释器进程，未清空OS文件缓存。热调用复用已导入模块。', '',
    '| 操作 | Node median / P95 ms | Python median / P95 ms | median变化 |', '|---|---:|---:|---:|']
regressions = []
for name, group, key in [('冷启动帮助', 'freshProcess', 'help'), ('冷启动换稿', 'freshProcess', 'replacePrompt'),
                          ('冷启动换图', 'freshProcess', 'replaceImage'), ('热换稿', None, 'inProcessPrompt'), ('热换图', None, 'inProcessImage')]:
    a = performance['results']['node'][group][key] if group else performance['results']['node'][key]
    b = performance['results']['python'][group][key] if group else performance['results']['python'][key]
    assert a['iterations'] == b['iterations'] == 20
    change = (b['medianMs']/a['medianMs']-1)*100
    lines.append(f'| {name} | {a["medianMs"]:.2f} / {a["p95Ms"]:.2f} | {b["medianMs"]:.2f} / {b["p95Ms"]:.2f} | {change:+.1f}% |')
    if change > 20 or b['medianMs']-a['medianMs'] > 50:
        regressions.append(name)
lines += ['', '11个完整视频payload逐值一致：正文/换行、媒体Data URL字节和图序不做宽泛字段忽略。新命名空间与JCS记录独立存储。', '',
    ('本轮超过20%或绝对50ms的median回归项：'+', '.join(regressions)) if regressions else '本轮未出现超过20%或绝对50ms的median回归。', '',
    '开发期间已修正稳定文件读取按128MiB上限预分配缓冲导致的额外成本，改为基于已核实文件大小读取并再次核对身份；文件校验未删除。微基准不覆盖远端排队/推理，也不保证另一设备相同速度。', '',
    '## 200项图片真本机HTTP', '',
    f'- 首个完整POST到达：{image["firstSendMs"]:.2f} ms；末个：{image["lastSendMs"]:.2f} ms；含全部登记总耗时：{image["totalMs"]:.2f} ms。',
    '- 200项全部请求体到达后才允许首个回包，归属以200张不同图片的实际SHA逐项核对；不是两路生成或默认100连接排队。',
    f'- 峰值RSS：{image["peakRssBytes"]/1024**2:.2f} MiB；事件循环延迟P95：{image["eventLoopLagP95Ms"]:.2f} ms，最大：{image["eventLoopLagMaxMs"]:.2f} ms。',
    '- RSS包含同进程pytest、假HTTP服务和合成图片；夹具为可压缩PNG，不能推导200个45MiB最坏响应的峰值。大响应按文件流式落盘后分两路解码，资源不足预检在POST前失败。',
    '- 等待分类：持久意图/账本I/O、响应接收、解码信号量和登记信号量；aggregateWaitMs是各任务等待之和，不能当作墙钟总时长。200项用Base64，下载峰值0；另有8张URL图片用真HTTP验证下载峰值2。',
    '- 同步持久化和大JSON解析仍可能造成事件循环延迟；测得最大值如上，未声称实时响应。任务取消停止新增，有界等待回执；没有通过削弱fsync/身份校验换速度。', '',
    '## 8段视频', '',
    f'8段总耗时{video["totalMs"]:.2f} ms；观测最大创建在途{video["maxCreates"]}，最大已知活跃{video["maxLive"]}。假服务创建延迟{video["syntheticCreateDelaySeconds"]}秒，下载延迟{video["syntheticDownloadDelaySeconds"]}秒。', '',
    f'本地冻结计划{video["prepareMs"]:.2f} ms；最终delivery核验/写入{video["deliveryMs"]:.2f} ms（后者已计入执行总耗时）。', '',
    '每段prepared/intent/send/taskId/terminal/downloadStart/downloadComplete均保留单调时钟值。假服务延迟与客户端耗时分开记录；前4创建同时在途，可信终态后5–8按序补位，下载最多2且不阻挡生成补位。', '',
    '[原始性能样本](reports/performance.json) · [200图时序/内存](reports/image-200.json) · [8段视频完整时序](reports/video-eight.json)', '']
(DOCS/'PERFORMANCE.md').write_text('\n'.join(lines), encoding='utf-8')

lines = ['# 离线验收记录', '', f'交付版本：**{__version__}**。本轮全部9个门槛真实执行成功；pytest **{counts["tests"]} passed，0 failed，0 errors，0 skipped**。', '',
    f'记录时间：{stamp}。Python：{verification["python"]}；解释器：`{verification["executable"]}`；平台：{verification["platform"]} / {verification["architecture"]}。', '',
    '| 实际命令 | 退出码 | 耗时秒 | 日志 |', '|---|---:|---:|---|']
for index, row in enumerate(verification['commands'], 1):
    command = ' '.join(row['command'])
    lines.append(f'| `{command}` | {row["exitCode"]} | {row["seconds"]:.2f} | [gate-{index:02}.log](reports/gate-{index:02}.log) |')
lines += ['', '## 必做场景与证据', '',
    '- 严格契约、UTF-16/非BMP、BOM/CRLF/末尾换行、7000限制、JCS、重复字段/无穷数：pytest及跨语言11条完整请求差分。',
    '- 6集11段同ID换图换稿：真实CLI子进程、其他资产/正文/引用保持、纯换稿禁止读取媒体与容量账本、并发替换无丢更新。',
    '- 200项图片真实本机HTTP：集中全部派发、独立乱序结果归属、DAG解锁；另测multipart真实字段/字节/MIME、URL下载2路、解码2路、登记1路、401/429/5xx/总超时/截断和无自动POST重试。',
    '- 8段视频真实本机HTTP：四创建并发、可信终态按序补位、慢下载不阻挡；新生成/部分复用/全复用身份准确，损坏和缺失文件不计为完整交付。',
    '- R3及多故事：无ID活owner保留、owner退出释放、真实GET失败释放、轮询预算结束保留、issued/applied/迟到终态吸收、恢复5held停止新增、旧损坏证据不覆盖更新活跃证据、遗漏slot登记、公平票据和每批次限额。',
    '- 真子进程杀停：视频意图后、POST中、回执后、状态保存前、容量事件后、下载rename前后；图片意图后/POST中/完整回执后/登记后；恢复未重复POST。',
    '- Windows真实OS锁、进程退出、稳定锁文件、事务中断恢复、共享拒绝下原子替换、junction/hardlink/ADS/UNC/大小写/身份变更。',
    '- 假凭据的真实DPAPI往返/备份与表单Host/Origin/token约束；仅本地配置状态不冒充远端认证。',
    '- 显式独立IR请求、恢复、语义审核、派生视频以及等价新准备绑定；普通视频无独立IR POST。',
    '- wheel安装到独立临时venv，PATH无Node/npm，审计钩子拒绝旧目录及工作区src访问；普通/旁白/tk三个真实Python进程各执行一次假视频、再次调用零POST复用。',
    '- 临时用户Skill安装/发现/引用/回滚及用户修改保护；六正文随wheel打包；未做全局安装。',
    '- ffmpeg/ffprobe生成并完整解码4秒合成视频+音频，错误哈希负例通过；其余小MP4结构夹具不冒充可播放片。', '',
    '## 来源与交付身份', '',
    f'- 旧参考：0.2.0 / `{after["commit"]}`；开工和收工Git状态均为空，远端未变。没有在旧目录构建或测试。',
    f'- 固定来源清单{len(source)}项，资源/helper清单{len(resources)}项；三个去噪TXT逐字节SHA保持，wheel资源独立。',
    '- 用户原始执行指令、完整方案和semantic-probe保存在docs/handoff。新项目没有Git提交或远端；旧提交只表示来源，不能当新代码提交号。交付文件SHA见ARTIFACTS.json。', '',
    '## 未做及未实机验收', '',
    '没有真实图片、视频、独立IR付费调用；没有远端凭据认证、余额或容量核验；没有GitHub推送/发布，没有读取旧Key或生产故事，没有全局Skill安装。', '',
    '实测环境为Windows AMD64/CPython3.14.5。Python3.13、Linux、macOS没有实机验收；TLS媒体DNS绑定实现没有经过真实供应商网络验收。路径前后身份检查与Windows拒绝用例不构成所有对抗性TOCTOU竞争均不可突破的证明。', '',
    '使用同一供应商账号正式切换时只启用一个提交引擎。新旧账本不共享四并发限制，不同Key也可能共享额度。R3释放本地容量不是远端取消，真实远端并发可能超过4。', '',
    '## 可复验入口', '',
    '`uv run --locked --no-sync python scripts/verify.py`；生成参考文档用scripts/build_reference_docs.py，发布本报告用scripts/finalize_reports.py，发行文件审计用scripts/audit_artifacts.py。', '',
    '[全量命令JSON](reports/verification.json) · [pytest XML](reports/pytest.xml) · [独立wheel烟测](reports/package-smoke.json) · [旧项目最终核对](reports/old-project-final.json) · [性能/内存](PERFORMANCE.md) · [源测试映射](SOURCE_TEST_MAP.md)', '']
(DOCS/'ACCEPTANCE.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps({'version': __version__, 'pytest': counts, 'oldProjectUnchanged': True, 'reports': str(DEST), 'performanceRegressions': regressions}))
