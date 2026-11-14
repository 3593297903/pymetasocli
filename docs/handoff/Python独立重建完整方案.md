# metasocli Python 独立重建方案

日期：2026-11-13。方案状态：设计与交接，尚未实现 Python 新项目。

参考基线：当前 `E:\metasocli`，版本 `0.2.0`，提交 `f4153c31c63d63c4ead8b2a470dbc5d31ad04d3c`。本轮已重新核对提交、主要契约、哈希/文本处理、图片客户端、视频工作流、R3 与替换入口。旧项目保持不变；未付费调用。

## 1. 推荐结论与方案比较

推荐：**独立 Python 模块化 CLI，保留当前业务行为，分阶段做离线等价验证，全部验收后再切换真实生成。**

目标是运行时以 Python 为主，不依赖 Node 调旧 CLI；保留 Codex Skill 作为用户入口，保留两个平台原有 API。先不同时引入数据库、Web 后台、常驻 Worker、分布式队列或新生成供应商。

| 方案 | 优点 | 代价/问题 | 结论 |
|---|---|---|---|
| A：Python 外壳调用旧 Node CLI | 快速搭入口，业务行为基本沿用 | 仍需 Node，旧系统耦合不消失，两套运行时更复杂 | 不符合这次独立 Python 内核目标 |
| B：Python 内核，按当前行为迁移 | 可独立安装；规则、模板、状态机可继承；风险可分阶段验证 | 必须重做类型、并发、Windows 文件与恢复实现 | **采用** |
| C：Python + SQLite + 服务端/Worker 全面重设计 | 适合未来多人、跨设备、UI | 一次改变语言、存储、调度和部署，回归面大 | 作为以后独立升级，不放入第一版 |

“最优”在此指适合当前单机、Codex 驱动、强调稳定和少往返的约束，不是任何场景的通用最优解。

## 2. 换成 Python 后会怎样

### 可以获得的收益

- 主业务与现有 Python 图片校验辅助统一语言，辅助校验改为进程内调用，减少重复启动子进程。
- 固定应用入口完成换图、换稿、准备和视频执行，Codex 不必再临时编排很多小脚本。
- 利用 asyncio 做网络等待、回执接收和任务补位，连接可复用，流式落盘。
- wheel + 独立虚拟环境部署；生产运行不需要 Node、npm、TypeScript。
- 通过清晰的领域层、应用层、存储接口和供应商接口，减少当前模块间的交叉依赖。

### 不能自动获得的收益

- 不会使供应商模型本身更快，也不会自动解决供应商队列、余额或网络故障。
- 不会自动消除 Codex 推理、等待用户和宿主审批间隔；要保留一次调用的流程设计。
- 不保证 CPU、内存或所有操作比 Node 更快；必须按同一输入实测。
- 不会消除未知创建结果；POST 超时仍可能已经被远端受理。
- 不会绕过或关闭宿主自动审核。

验收目标是行为正确、可恢复、一次调用和无明显本地性能退化；不预先承诺“快几倍”或“绝不失败”。

## 3. 新项目身份与隔离

新任务采用用户实际新建目录作为 `PY_ROOT`。未指定时建议 `E:\metasocli-py`；不能在 `E:\metasocli` 内覆盖重写。存在其他项目的目录不能强制初始化。

| 项目 | Python 新项目 | 原项目 |
|---|---|---|
| 包/CLI | `metasocli-py` | `metasocli` |
| Python import | `metasocli_py` | 不适用 |
| 新版本 | 开发期 `0.1.0a1`，完成验收后 `0.1.0` | `0.2.0` |
| 故事清单 | `metasocli-py.yaml` | `metasocli.yaml` |
| 故事状态目录 | `.metasocli-py` | `.metasocli` |
| 默认用户配置 | `%USERPROFILE%\.metasocli-py` | 旧安装 `.local` |
| 默认运行账本 | `%USERPROFILE%\.metasocli-py-runtime` | `.metasocli-runtime` |
| Metaso 环境变量 | `METASOCLI_PY_METASO_API_KEY` | `METASO_API_KEY` |
| 图片环境变量 | `METASOCLI_PY_IMAGE_API_KEY` | `METASOCLI_IMAGE_API_KEY` |
| 测试配置/账本覆盖 | `METASOCLI_PY_CONFIG_DIR`、`METASOCLI_PY_RUNTIME_DIR` | 不使用旧变量 |

新程序不得自动读取旧密钥、授权文件和运行账本，不做双向同步，不在旧故事原地转换。旧源码只读；不复制 `.git`、node_modules、真实故事、密钥、旧生产账本。测试使用新项目内隔离目录。

**新旧程序若使用同一个平台账号，并行运行时两套本地账本不会合并。** 正式切换时，同账号仅启用一种提交引擎，先核对旧任务；不能宣称新旧加起来仍自动受四并发限制。不同 Key 也可能属于同一账号配额。

## 4. Python 技术选型

| 层次 | 选择 | 约束 |
|---|---|---|
| Python | 标准 CPython 3.13/3.14，优先复用已可用的 3.14 | 初始支持范围 `>=3.13,<3.15`；只宣称实际测试的平台/版本；不用 free-threaded 实验环境 |
| 环境/依赖 | uv、`.venv`、`pyproject.toml`、`uv.lock` | 首次解析后锁定实际版本，安装用 `--locked --link-mode copy` |
| 构建 | Hatchling / wheel | 包内带模板、Skill 正文、去噪文本；正常运行不触发依赖同步 |
| CLI | 标准库 argparse | 不为命令解析额外引入 Web/GUI 框架 |
| 契约 | Pydantic 2.x | strict、extra forbid、字段级验证；不输出含完整输入的默认 ValidationError |
| 网络 | HTTPX AsyncClient | 复用客户端，显式等待、连接池、代理、TLS、重定向和重试策略 |
| 并发 | asyncio | 持久化状态驱动，任务错误隔离，不以协程内存列表作为唯一真相 |
| YAML | PyYAML 的受限 SafeLoader | 拒绝重复键、alias/anchor、非预期隐式类型；读取体积有上限 |
| 图片校验 | Pillow | 只验证、不自动改尺寸/旋转/重编码；限制像素、帧数、文件大小 |
| 跨进程锁 | portalocker 排他锁 + 项目封装 | 稳定锁文件，实际 OS 锁判断占用；锁元数据与业务任务分离 |
| 结构化哈希 | rfc8785 + SHA-256 | 新命名空间使用明确 `jcs-sha256-v1`，不伪装旧 canonicalHash |
| 凭据 | Windows DPAPI（ctypes 调用系统 API）；其他平台先用独立环境变量 | 新配置目录，禁止自动明文落盘，不依赖 PowerShell 子进程解密 |
| 测试 | pytest、pytest-asyncio、Hypothesis；ruff + mypy | 模拟 HTTP、真子进程故障、性质测试和类型/格式检查 |

确切补丁版本由新任务核实官方稳定版本并写入 uv.lock，本方案不捏造未安装的版本。`.python-version` 记录实际通过验证的解释器版本。uv 的 `--locked` 会在锁文件与项目不一致时报错，不能以 `--frozen` 掩盖这种不一致。[uv 官方文档](https://docs.astral.sh/uv/concepts/projects/sync/)

Pydantic 默认会转换部分输入类型，因此必须针对原契约启用严格校验；JSON 字符串、UUID、时间戳和内部 Python 类型的入口要明确区分。[Pydantic 严格模式](https://docs.pydantic.dev/latest/concepts/strict_mode/)

## 5. 建议目录与依赖方向

```text
PY_ROOT/
├─ pyproject.toml / uv.lock / .python-version
├─ AGENTS.md / README.md
├─ src/metasocli_py/
│  ├─ __main__.py / cli.py / version.py
│  ├─ contracts/        Story、Plan、Job、Batch、Image、Receipt、Retry
│  ├─ domain/           原文、UTF-16、旁白、时长、ID、纯状态决定
│  ├─ application/      初始化、导入、换图、换稿、图片准备、视频一次执行
│  ├─ images/           图片 DAG、all-ready 调度、接收与登记
│  ├─ video/            范围冻结、批次、创建、轮询、下载、R3、票据
│  ├─ providers/        Metaso、Yiciyuang、HTTP 传输
│  ├─ persistence/      路径、锁、原子文件、仓储、哈希、恢复证据
│  ├─ media/            图片、MP3/WAV、MP4 技术验证
│  ├─ credentials/      DPAPI、配置解析、短时本机连接表单
│  ├─ telemetry/        分阶段计时、摘要、错误脱敏
│  └─ resources/        原样模板、去噪正文、Skill 与规则资料
├─ .agents/skills/      六个新命名入口
├─ tests/
│  ├─ unit/ contract/ integration/ process/ offline_http/
│  ├─ properties/ golden/ benchmarks/ packaging/
│  └─ fixtures/        合成故事与媒体，不放真实用户业务
├─ scripts/            离线验收、wheel smoke、基准测试
├─ docs/               架构、来源映射、兼容矩阵、验收、部署
└─ .work/              临时测试和无密钥报告
```

依赖方向：CLI → application → domain/contracts；application 通过明确的 Repository、Provider、Clock、FileStore 接口访问 persistence/providers。domain 不反向 import CLI/网络；供应商适配器不直接修改 Story；构建模块对象不能读取 Key 或发请求。

保留必要接口即可，不引入插件系统、事件总线服务或泛化 Workflow 引擎。原有 Python helper 复制到新包后作为模块调用，不再每个操作启动独立 Python；保留其 CLI 包装以支持单独校验。

## 6. 当前实现到 Python 的迁移映射

| 当前源码 | 新模块 | 必须保留的语义 |
|---|---|---|
| contracts/*.ts | contracts/*.py | 严格契约、可选/空值区别、状态、输入范围 |
| core/project.ts | application/import_story.py + domain/story.py | 原文完整、分段连续、ID 稳定、配方冲突与依赖环校验 |
| core/prompt-replacement.ts | application/replace_prompt.py | 同集/段 ID，一次事务，其他段正文不变，安全旁白重定位 |
| assets/registry.ts | application/replace_asset.py + media | 同资产 ID、真实文件哈希、只更新选中 media |
| core/planning.ts、metaso/h3.ts | video/planning.py + providers/metaso.py | 输入冻结、H3 参数、引用顺序、旁白与 true IR |
| images/preparation/reporting | application/prepare_images.py、collect_images.py | 集中准备、恢复准备进度、从回执收尾、不重复登记 |
| images/planning/run/result | images/*.py | DAG、all-ready、完整响应证据、一次性重试与下载恢复 |
| jobs/video-run/scope/workflow | application/run_video.py + video/scope.py | 一次调用准备/执行/下载/交付，批次身份与 reused 语义 |
| jobs/batch/submit/resume | video/scheduler.py、submit.py、resume.py | 四并发、补位、先意图后 POST、先回执后状态 |
| jobs/coordinator/capacity-events/policy | video/capacity.py、capacity_events.py、dispatch.py | R3、终态优先、ID 恢复、派发票据和共享上限 |
| jobs/video-retry/batch-retry/submission-guard | video/retry.py、guard.py | 旧未知保留，一次新尝试授权，不强求不存在的 taskId |
| storage/* | persistence/* | 安全路径、稳定读取、原子写、锁与恢复窗口 |
| metaso/credentials、images/credentials | credentials/* | 独立凭据、脱敏、本地配置与远端认证分开报告 |
| skills 与已有 Python 脚本 | resources + 新 Skill | 模板正文保持，改执行入口与命名空间 |

`h3-inline-ir` 主链必须第一版完整实现。独立 `context-ir` 兼容支路列入完整功能清单，在主链之后移植并离线验证；未完成时不能声称新项目已覆盖旧项目全部能力。

## 7. 跨语言兼容必须明确处理

### 7.1 UTF-16 与字符位置

当前 start/end 和旁白 cues 是 UTF-16 code unit。Python 的 `len`/切片不能直接替代。

本轮实测 `甲😀乙`：JavaScript 长度 4、Python 长度 3；原范围 `[3,4)` 是“乙”，Python 直接 `[3:4]` 得到空字符串。结果保存在 [语义对照记录](E:/metasocli/.work/python-rebuild-plan-20261113/semantic-probe.json)。

新 Story/draft 明确 `offsetEncoding=utf16`；提供 length/slice/boundary/offset-map 函数，拒绝切开代理对。渲染后的 H3 7000 字符限制仍按 Unicode 码点检查。保留仅去首 BOM、规范 CRLF/CR 的规则，不自动 strip 空格、结尾换行，不做 NFC/NFKC 改写。

### 7.2 哈希不是直接替换 json.dumps

当前 canonical.ts 使用 `localeCompare(..., 'en')` 排序再 JSON.stringify。本轮数值/大小写样本证明 Python `json.dumps(sort_keys=True)` 得到不同字节与哈希；旧实现也不能直接当作 RFC 8785。

新记录采用带版本的 JCS 哈希协议，使用经过测试的 RFC 8785 实现，不自己写浮点序列化。对象的 `hash` 字段在哈希前按契约排除，数组顺序不改变；NaN/Infinity/非法 surrogate 拒绝；超安全整数范围的计数拒绝或改为明确字符串字段，远端 taskId 始终为字符串。文件和完整正文仍直接对实际 UTF-8/文件字节做 SHA-256。[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)、[Python 实现](https://github.com/trailofbits/rfc8785.py)

这意味着：**行为、媒体字节、文本与有序引用可等价，新计划/账本的结构化哈希不承诺等于旧版。** 不重算旧哈希后覆盖旧记录，不把新 hashVersion 套在旧 run 授权上。差分验证比较业务语义和发送内容，随机 ID、时间、命名空间、明确版本化哈希另行核对。

### 7.3 输入类型、时间与文件身份

- 禁止把布尔值当作整数、把字符串“12”自动当成时长；有限数字、向上取整、4–15 秒规则与基线一致。
- 模型 dump 必须区分未提供、null、false、0，不能全局 exclude_none 导致身份变化。
- YAML/JSON 拒绝重复字段，保证序列顺序；不接受 alias 扩展造成的隐式共享对象。
- JSON 时间统一 UTC ISO 字符串；耗时用 monotonic/perf_counter，不能用可跳变的墙钟算预算。
- 路径不是 `resolve()` 一次就安全：Windows reparse/junction、硬链接、大小写、保留名、ADS、UNC、文件身份改变都要测试。

## 8. 图片执行设计

保持 `images prepare → images run → images collect` 三个职责。prepare、collect 不偷偷提交生成。主机只做一次集中内容准备，不退回逐集生成循环。

### 请求与默认参数

- 图片 origin：`https://api.yiciyuang.com`。
- 无参考图：`POST /v1/images/generations` JSON。
- 有参考图：`POST /v1/images/edits` multipart；单图 `image`，多图重复 `image[]`，使用 list of tuples，不能用会覆盖重复字段的普通 dict。
- 模型 `gpt-image-2.5`、`n=1`、默认 quality medium、response_format url，同时支持 b64_json。
- 人物/场景/道具默认 1920×1088；首帧 1088×1920；允许原 profile 中已实现的显式尺寸。
- 人物、场景、道具三类去噪正文原样保留，按类型只追加一次；在算配方哈希前完成。
- 图片默认总等待 600 秒；显式配置最长 1200 秒；保留明确 exact=300 秒的能力。不得把 ms 原样当作 HTTPX 的秒。
- 下载并发 2、解码校验并发 2、登记 1；自动 POST 重试为 0。

all-ready 仍是每项一个请求，满足依赖的项目尽快派发；不能改成每次两张或一集一集。已知 concurrent/RPM/batch 限制必须遵守。HTTPX 连接池缺省最多 100 连接，不能让它无声改变 200 项集中派发的承诺；图片生成连接池显式配置，通常 `max_connections=None`，资源预检不足时在 POST 前清楚报告，不偷偷换成固定小队列。[HTTPX 连接池](https://www.python-httpx.org/advanced/resource-limits/)

### 接收与异常

保存 request intent → 接收响应头 → **流式保存响应体** → fsync/完整性证明 → 解析 → URL 下载或 Base64 解码 → 图片技术校验 → 正式登记。完整响应与结果均绑定 operationId/requestHash，不按文件名猜归属。

不能让 200 个 `.post()` 同时把大 Base64 响应完整留在内存；使用流式 API，最多两项解码/图片验证。任务结束才登记会延迟依赖解锁，因此每项一完成即登记并唤醒依赖项。HTTPX 支持 AsyncClient 与流式响应，应复用客户端并关闭响应资源。[HTTPX 异步与流式接口](https://www.python-httpx.org/async/)

图片失效时先恢复原完整响应或原 URL。明确拒绝、确定失败、未知分别保存；无响应不能推断供应商未受理。同一故事未知结果的正式恢复/重试规则照旧，外部故事未知不能变成无条件全局阻塞；已知配额占位仍按真实规则处理。

## 9. 视频一次执行设计

完整顺序：

```text
video run（一次）
→ 捕获当前版本、资产、提示词和有序选段
→ 冻结范围/计划并核对交接身份
→ R3 容量检查与派发票据
→ 一次性授权范围落盘
→ 最多四个创建请求在途，异步接收 taskId
→ 原 taskId 查询
→ 可信终态释放生成名额，优先补下一段
→ 下载并发二路，结果验证与原子保存
→ delivery + timings + 正确 reused 标记
```

当前 API 不变：`POST https://metaso.cn/api/minimax/v2/video_generation`，查询为对应 `query/video_generation/<taskId>`。默认 `MiniMax-H3`、`context_ir_enabled=true`，768P/9:16/水印 false；保留显式参数与 9 图、1 旁白、首帧互斥、7000 字符、64 MiB 限制。

创建默认 120 秒，单次查询 30 秒，缺省轮询 60 次/5 秒；这不是总流程固定 300 秒。单任务查询/下载不创建新任务，批次 resume 仅能提交已有冻结授权内尚未开始项。

保留以下已经修好的行为：

- 同资产 ID 换图之后，新计划使用新图片，旧已受理任务不改输入。
- 同集/段 ID 换稿后，未提交旧计划失效；已受理任务按旧 ID 恢复。
- 完成一个生成就补一个，不等这条下载完，不等另外三个都结束。
- prepared→提交→taskId→下载的关键崩溃窗口有持久化证据恢复。
- 本次刚生成的结果不能标成“启动前已复用”；混合复用按项准确报告。
- 视频技术检查不自动升级为视觉/剧情评审；没有字幕/剪辑等新增生产步骤。

## 10. R3 与未知重试原样保留

Python 项目用自己的 video-ledger，**沿用 R3 的业务决策，不共用旧文件协议**。

| 事实 | 容量决定 |
|---|---|
| 无 taskId 且创建已经结束，或提交 owner 已退出 | released，旧 unknown 与原错误保留 |
| 真正的 owner 正在创建/保存回执 | held，不能因暂缺 taskId 抢走它 |
| 实际 GET 失败/超时/无法确认身份，或来源证据失效 | 按 R3 released，保留 ID 和证据 |
| 已明确 queued/running，仅本地停止或轮询预算耗尽 | held，不按时间长短释放 |
| 匹配身份的可信终态 | released；不能被迟到 running 复活 |
| 后续新匹配证据证实活跃 | 恢复 held；超过四个就停止新增 |

终态事件、观察 issued/applied 水位、ID 修复、lastRelease/lastRestore 要保留；事件不是第二本独立容量真相。迟到回执、错误 ID、旧 queued 状态不得覆盖更新事实。

派发票据保留原范围和剩余序号；先进入且仍有待提交段的批次优先补位，真实余位可以给其他项目；待提交清空后让出，不等下载。没有活跃进程时不后台清理；status/doctor 不修改容量。

释放本地容量不等于取消远端任务，因此仍不承诺远端绝对四并发。旧未知不能靠换 plan/run 重新提交。用户明确授权某段一次新尝试时，保留 retryOf 和授权范围，不要求不存在的旧 taskId，不自动扩展无限重试。

## 11. 并发、锁、停止与网络细节

### 锁与原子文件

- 进程内用明确的异步互斥；跨进程用 portalocker 排他锁。普通 JSON 记录继续临时文件 + fsync + os.replace，Windows 替换竞争有界重试，禁止先删目标。
- OS 锁使用稳定文件，不随每次 release 删除/替换；元数据另存。进程退出后锁句柄释放，但业务 unknown/queued 不能因此自动变“完成”。所有参与者须遵守同一协议。[Portalocker 官方说明](https://portalocker.readthedocs.io/en/latest/)
- 调度/操作 lease 可以覆盖远端处理生命周期；共享账本/Story 写锁只保护短事务，不在其内等待 HTTP、Pillow 解码或用户输入。
- 避免跨域嵌套锁；确需同时持有短事务锁时固定 runtime→story 顺序；story 事件先落盘，释放 story 锁再应用 runtime。无反向路径和无跨两个故事同时持锁。
- CAS/版本校验用于阻止“锁外读到旧状态，锁内覆盖新改动”。结果和计划的快照身份不能只用 mtime 替代内容哈希。

### 协程错误与停止

Python TaskGroup 的一项未处理异常会取消同组其他任务，不能直接把所有付费提交包进裸 TaskGroup。一项业务错误应保存成结构化结果，按规则停止新增，其他已提交请求仍尽量接收回执；外部取消要有显式处理。[asyncio TaskGroup 文档](https://docs.python.org/3.13/library/asyncio-task.html#task-groups)

Ctrl+C/停止：停止派发，保存状态并退出；不能自动重发、假装取消远端或清空账本。无回执创建视为 unknown；已知 ID 保存用于后续恢复。少量回执关键写入可以 shield，必须有界，不能无限忽略用户停止。阻塞文件/图片工作在线程中运行时，取消不会强制停掉线程，恢复与关闭流程也要测试。

### HTTP 等待与代理

HTTPX 默认是 5 秒网络无活动超时，而且 connect/read/write/pool 分别计时；它不是整个请求总时限。使用明确的 HTTPX 分项值加 `asyncio.timeout(total_seconds)` 覆盖发送和完整响应接收，避免再次出现外层 600 秒、底层提前结束的问题。[HTTPX 超时文档](https://www.python-httpx.org/advanced/timeouts/)

网络模式按供应商保存 `direct|proxy|environment`，新配置缺省 direct（HTTP 客户端层）；direct 使用 trust_env=False，proxy 仅使用明确配置，environment 才继承环境代理。不得静默根据环境改变路径；不改系统代理，direct 也不意味着绕过 TUN。HTTPX 默认读取代理环境变量，需要显式控制。[HTTPX 环境变量](https://www.python-httpx.org/environment_variables/)

TLS 校验开启；API 创建不跟随重定向、不带自动重试。图片下载按当前限制，视频下载允许至多三次经过 public HTTPS 检查的重定向，绝不把 API Key 转发给素材域名。禁止私网/回环媒体 URL、签名 URL 全量日志。

## 12. 三个成品 Skill 和两个替换入口

新名字固定：

```text
metasocli-py
metasocli-py-video-prompts
metasocli-py-video-prompts-旁白
metasoclitk-py
metasocli-py-prompt-engine
metasocli-py-reference-images
```

六个项目入口只读新包正文；三个成品入口都把纯换图、纯换稿、已有内容生成视频的短分支放在普通全文准备之前。

- 换图：`assets register --id <原ID> --file ...`，一次调用读新图/校验/保存/更新 media/返回。不得重导全剧、改配方/正文/引用、重建图库。
- 换稿：`prompts replace --episode <原ID> --segment <原ID> --file ...`，一次调用。保留时长、素材和引用顺序，其他段仅维护字符偏移而不改正文。旁白唯一同句可安全重定位，有歧义明确失败，不随意猜。
- 视频：`video run ... --confirm` 一次串起准备、执行和交付；已准确 batchId 按原 ID 恢复。
- 只换图或换稿时，做到回执返回即结束，不顺便生图/视频或让模型反复查看所有资产。

用户级入口使用新名，安装前确认实际发现目录且不覆盖同名外来技能。Skill 允许继承旧模板业务规则，但不得复制旧本机授权原文来冒充新项目已得到付费授权。三个去噪文本与模板的原始哈希要独立校验；资源通过包路径读取，不能依赖启动 cwd 或旧 E 盘位置。

## 13. 凭据与迁移

提供 Python 原生 `auth connect` / `images auth-connect` 临时 localhost 表单，随机 token、短有效期、Host/Origin/请求大小校验、不记录输入。新增/更换 Key 都要加密后回读验证再原子替换，保留原密文备份；字段不可进入命令行、聊天、环境报告。离线测试使用合成假 token，不加载旧 Key。

本次只做离线实现，因此无需真实 Key，也不能自行做收费验收。auth status 的报告区分本地结构配置、解密检查、远端认证和付费生成；不能看到 configured=true 就宣称远端可用。

第一版以新故事为主。另做只读 `legacy inspect` 与显式 `legacy import-content`：仅从已静止、无活跃/未知操作的旧故事单向复制内容和已验证媒体到全新故事；分配新 projectId，保留集/段/资产 ID，记录来源映射。不得迁移旧运行账本或把历史任务伪装为 Python 新执行。

有进行中/unknown 任务的旧故事只给只读报告，在旧版恢复；跨引擎接管活跃任务不纳入第一版。历史成片可以作为带来源的归档文件复制，不能据此伪造新任务已完成。旧故事永不原地修改。

## 14. 实施阶段与完成标准

| 阶段 | 实施内容 | 必须交付 |
|---|---|---|
| P0 基线冻结 | 只读固定提交，抽取业务/命令/错误/默认参数/测试场景；登记模板来源 | SOURCE_BASELINE、FEATURE_MATRIX、BEHAVIOR_CONTRACT、基准夹具 |
| P1 基础设施 | Python 包、契约、UTF-16、JCS、路径、原子写、锁、凭据接口、无网测试护栏 | 能安装的 wheel、基本 CLI、基础故障测试 |
| P2 本地业务 | init/import/assets/prompts/plan/doctor 与三个 Skill 短入口 | 两个替换入口差分通过、零网络证明 |
| P3 图片全流程 | prepare/plan/run/collect、DAG、URL/Base64、完整回执、重试恢复 | 200 项假服务并发与进程中断测试、素材归属校验 |
| P4 视频全流程 | video run/batch/单任务、R3/票据、未知重试、下载交付；再补独立 IR | 8 段持续补位、多故事、迟到事件、全部恢复窗口 |
| P5 打包与验收 | 六个 Skill、可选旁白、凭据表单、导入边界、性能/内存、无 Node 安装测试 | 验收报告、操作说明、版本、回退边界 |

每阶段允许独立提交新仓库检查点；分支用 `codex/`。未要求不推送、发布或覆盖旧项目。不能做完骨架就宣称完成；必做功能全部过关才能标 Python 0.1.0 已离线可用。真实服务验收单独等用户以后指定样本和次数授权。

## 15. 必须通过的离线验收矩阵

| 组 | 验收内容 |
|---|---|
| A 纯度与安装 | 没有 Node/npm 时 wheel 中的主链仍可运行；不得 subprocess 旧 CLI；包内模板完整；启动不访问旧目录/Key |
| B 文本 | 中文、emoji、非 BMP、CRLF、BOM、末尾换行、旁白定位、7000 限制；不截断/改写 |
| C 哈希/契约 | JCS 官方向量、数字/空值/字段顺序、非法数、旧算法隔离；不错误继承旧授权 |
| D 换图 | 6 集/11 段合成故事：一个 ID 换图一次；新请求用新图，原文、配方和引用不变；零网络 |
| E 换稿 | 相同集/段 ID、其他段正文/时长/图片不变；UTF-16 偏移维护；旁白歧义不误绑定；零媒体读取/账本访问 |
| F 图片 | 200 项假请求均启动且回执归属正确；依赖图自动解锁；无任意两并发限制；URL、b64、错误 MIME/尺寸/截断响应 |
| G 部分失败 | 一图失败不取消已发送的其他图；401/429/5xx 分类保持；下载坏了不重生；未知没有自动 POST |
| H 视频补位 | 8 段，前四个进入创建；终态一出现第5个按序补入，不能等下载；上限与每批次1–4附加限制正确 |
| I R3 | 无 ID owner 活/死、GET失败、POLL_LIMIT、终态迟到、ID冲突、活跃恢复到5、观察水位、重复事件幂等 |
| J 多项目 | A图片未知不全局卡B；A批次补位优先；A并发1给B余位；票据退出让出；账本真实损坏不放行 |
| K 崩溃恢复 | 意图后/POST中/回执后/任务更新前/容量事件后/下载重命名前后杀进程；恢复不重复生成 |
| L 一次入口 | 三个成品 Skill 静态规则正确；真实 Python CLI 子进程一次完成选段→假生成→下载→delivery；混合复用标记正确 |
| M 锁与文件 | 双进程竞争、并发替换、Windows短暂拒绝、不可读owner、junction/hardlink、越界；不偷锁删证据 |
| N 凭据/网络 | 假token DPAPI往返、替换失败原值保留、日志无token；总/分项超时、代理模式、连接池、资源关闭 |
| O 兼容支路 | 明确启用的独立 IR、IR审核/派生；主入口仍只走内联IR |

pytest 中默认拦截外网 socket/HTTP；本机假 HTTP 服务白名单与生成 transport 注入明确。不能只 mock 一个函数就把真实 multipart、连接池、流式接收或跨进程锁算作已验收。必要超时场景可用比例缩短的可注入 Clock 测试，另做小数量真实本地时间测试，不等真实 600 秒才验证机制。

将现有约 55 个测试文件里的业务场景逐项映射到新测试，而非只追求相同用例总数。记录命令、退出码、通过/失败/跳过；跳过不能算通过。

## 16. 性能与内存验收

保留固定入口是主要提速手段，不为各小步骤多次回到 Codex。

- 本地换图/换稿：同机同合成输入，冷启动与预热分开；预热至少20次，报告 median/P95。主目标是较 TS 基线无明显退化，建议 median 回归超过20%或绝对增加超过50ms时解释并优化，不删校验凑指标。
- 视频8段：用完全相同的假创建/完成延迟，记录每段 dispatch、taskId、terminal、补位、download；不能通过减少轮询正确性/必要持久化获得虚假提速。
- 图片200项：记录首个/最后一个请求进入传输的时间、连接池等待、回包、解码、登记；已知依赖等待单列。
- 峰值内存与事件循环延迟单列；内存不得随200个最大响应完整缓冲成倍增长。使用流式文件、二路解码、二路下载和有界线程任务。
- H3 编码最多为正在提交的请求保留大 body，不常驻全部剧集的 Base64；每段规划计算后释放临时内容，快照/哈希校验仍保留。
- 所有测试结果是本地数据，不推断远端模型耗时；未做基准前不宣称比旧版快。

## 17. 交付物与边界

新任务最终应交付：可安装 Python 包、完整源码、锁文件、六个项目 Skill、三个成品跨项目入口的安装说明、来源清单、功能映射、离线验收报告、逐阶段计时、迁移边界、普通/旁白/tk 使用说明和无密钥的配置指令。

旧 Node 项目继续保留可用；第一版不替换旧全局命令，不修改旧 Skill，不碰旧生产账本。以后要真正切换生产，需要停旧提交、独立配置两套新 Key 或经用户明确选择重配同账号、做单独获准的少量真实测试，再启用 Python 的正式入口。

对应的新任务执行指令见 [给新项目 Codex 的完整指令](E:/metasocli/.work/python-rebuild-plan-20261113/给新项目Codex的执行指令.txt)。
