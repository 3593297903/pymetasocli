# 当前修订：图片 C＋视频 F

**CF-PERF-20261113-R1，版本 0.1.0，2026-11-13。** 本次实际全量 **125 passed，0 failed，0 errors，0 skipped**；Ruff、mypy（50 源文件）、离线构建、无 Node 的独立 wheel 三入口烟测全部通过。原 110 项逐字节保留，新增 15 项；30 张三组轮换、200 张一组及提前返回前后对照全部完成，资产映射正确、重复 resume 零 POST，原 11 条完整请求差分仍相同。

视频 F 包含晚唤醒补强，并保留已开始 GET 的正常回执处理。三个 Skill、入口、模型/API/超时/依赖/引用顺序等未改。真实付费调用 0；没有真实接口验收、生产数据操作、推送或全局 Skill 修改。首次沙箱临时目录 ACL 错误和审批重跑均有日志。

[本次完整验收、性能与回退](CF_PERF_20261113_R1.md) · [本次 pytest XML](reports/cf-20261113-r1/pytest.xml) · [本次结构化结果](reports/cf-20261113-r1/summary.json) · [最终发行哈希](ARTIFACTS.json)

---

以下保留先前 110 项修复验收的历史记录；不将其命令与时间冒充本次结果。

# 离线验收记录

交付版本：**0.1.0**。本轮全部9个门槛真实执行成功；pytest **110 passed，0 failed，0 errors，0 skipped**。

记录时间：2026-11-13T08:47:12.703604+00:00。Python：3.14.5 (tags/v3.14.5:5607950, May 10 2026, 10:43:50) [MSC v.1944 64 bit (AMD64)]；解释器：`E:\pymetaso\.venv\Scripts\python.exe`；平台：Windows-10-10.0.19045-SP0 / AMD64。

| 实际命令 | 退出码 | 耗时秒 | 日志 |
|---|---:|---:|---|
| `uv sync --locked --link-mode copy` | 0 | 0.03 | [gate-01.log](reports/gate-01.log) |
| `uv run --locked --no-sync ruff check .` | 0 | 0.05 | [gate-02.log](reports/gate-02.log) |
| `uv run --locked --no-sync mypy src/metasocli_py` | 0 | 0.44 | [gate-03.log](reports/gate-03.log) |
| `uv run --locked --no-sync python -m pytest --junitxml=.work/reports/pytest.xml` | 0 | 287.00 | [gate-04.log](reports/gate-04.log) |
| `uv build` | 0 | 5.84 | [gate-05.log](reports/gate-05.log) |
| `E:\pymetaso\.venv\Scripts\python.exe -m metasocli_py --version` | 0 | 0.22 | [gate-06.log](reports/gate-06.log) |
| `E:\pymetaso\.venv\Scripts\python.exe -m metasocli_py --help` | 0 | 0.22 | [gate-07.log](reports/gate-07.log) |
| `uv run --locked --no-sync python scripts/package_smoke.py` | 0 | 10.45 | [gate-08.log](reports/gate-08.log) |
| `uv run --locked --no-sync python scripts/benchmark.py` | 0 | 82.44 | [gate-09.log](reports/gate-09.log) |

## 必做场景与证据

- 严格契约、UTF-16/非BMP、BOM/CRLF/末尾换行、7000限制、JCS、重复字段/无穷数：pytest及跨语言11条完整请求差分。
- 6集11段同ID换图换稿：真实CLI子进程、其他资产/正文/引用保持、纯换稿禁止读取媒体与容量账本、并发替换无丢更新。
- 200项图片真实本机HTTP：集中全部派发、独立乱序结果归属、DAG解锁；另测multipart真实字段/字节/MIME、URL下载2路、解码2路、登记1路、401/429/5xx/总超时/截断和无自动POST重试。
- 8段视频真实本机HTTP：四创建并发、可信终态按序补位、慢下载不阻挡；新生成/部分复用/全复用身份准确，损坏和缺失文件不计为完整交付。
- R3及多故事：无ID活owner保留、owner退出释放、真实GET失败释放、轮询预算结束保留、issued/applied/迟到终态吸收、恢复5held停止新增、旧损坏证据不覆盖更新活跃证据、遗漏slot登记、公平票据和每批次限额。
- 真子进程杀停：视频意图后、POST中、回执后、状态保存前、容量事件后、下载rename前后；图片意图后/POST中/完整回执后/登记后；恢复未重复POST。
- Windows真实OS锁、进程退出、稳定锁文件、事务中断恢复、共享拒绝下原子替换、junction/hardlink/ADS/UNC/大小写/身份变更。
- 假凭据的真实DPAPI往返/备份与表单Host/Origin/token约束；仅本地配置状态不冒充远端认证。
- 显式独立IR请求、恢复、语义审核、派生视频以及等价新准备绑定；普通视频无独立IR POST。
- wheel安装到独立临时venv，PATH无Node/npm，审计钩子拒绝旧目录及工作区src访问；普通/旁白/tk三个真实Python进程各执行一次假视频、再次调用零POST复用。
- 临时用户Skill安装/发现/引用/回滚及用户修改保护；六正文随wheel打包；未做全局安装。
- ffmpeg/ffprobe生成并完整解码4秒合成视频+音频，错误哈希负例通过；其余小MP4结构夹具不冒充可播放片。

## 来源与交付身份

- 旧参考：0.2.0 / `f4153c31c63d63c4ead8b2a470dbc5d31ad04d3c`；开工和收工Git状态均为空，远端未变。没有在旧目录构建或测试。
- 固定来源清单254项，资源/helper清单19项；三个去噪TXT逐字节SHA保持，wheel资源独立。
- 用户原始执行指令、完整方案和semantic-probe保存在docs/handoff。新项目没有Git提交或远端；旧提交只表示来源，不能当新代码提交号。交付文件SHA见ARTIFACTS.json。

## 未做及未实机验收

没有真实图片、视频、独立IR付费调用；没有远端凭据认证、余额或容量核验；没有GitHub推送/发布，没有读取旧Key或生产故事，没有全局Skill安装。

实测环境为Windows AMD64/CPython3.14.5。Python3.13、Linux、macOS没有实机验收；TLS媒体DNS绑定实现没有经过真实供应商网络验收。路径前后身份检查与Windows拒绝用例不构成所有对抗性TOCTOU竞争均不可突破的证明。

使用同一供应商账号正式切换时只启用一个提交引擎。新旧账本不共享四并发限制，不同Key也可能共享额度。R3释放本地容量不是远端取消，真实远端并发可能超过4。

## 可复验入口

`uv run --locked --no-sync python scripts/verify.py`；生成参考文档用scripts/build_reference_docs.py，发布本报告用scripts/finalize_reports.py，发行文件审计用scripts/audit_artifacts.py。

[全量命令JSON](reports/verification.json) · [pytest XML](reports/pytest.xml) · [独立wheel烟测](reports/package-smoke.json) · [旧项目最终核对](reports/old-project-final.json) · [性能/内存](PERFORMANCE.md) · [源测试映射](SOURCE_TEST_MAP.md)

## 本轮独立核验修复

PY-01/PY-02/PY-03已实际修复并完成本轮110项离线验收。修前3 failed、修后3 passed；原76项保留。prepared兼容、旧孤位保护、进程中断、GET/POST计数、调度耗时及新增持久化开销见 [完整修复验收](RECOVERY_FIX_20261113.md)。没有真实接口验收。
