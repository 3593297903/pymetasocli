# 功能与差异矩阵

对照固定提交 `f4153c31c63d63c4ead8b2a470dbc5d31ad04d3c`，完整读取 54 个 TypeScript 测试文件、1 个 Python Skill 测试文件及相关源码/文档。下表按业务能力映射，不以文件数或 pytest 项数证明逐行等价。逐文件对应关系在 [SOURCE_TEST_MAP.md](SOURCE_TEST_MAP.md)，最终实际结果在 [ACCEPTANCE.md](ACCEPTANCE.md)。

| 基线能力 | Python 入口 / 实现 | 离线证据 |
|---|---|---|
| 剧本、成品提示词、连续来源 | init / import；application/story.py | 中文/emoji/BOM/CRLF/末尾换行、严格契约、来源事务 |
| 旁白归属与 H3 输入 | UTF-16 cues；video/planning.py | WAV/MP3 容器、float WAV/VBR/ID3、唯一 cue 重定位、三入口 wheel 烟测 |
| 同 ID 纯换图 | assets register | 6集11段、原ID/图序/其他资产保持、真实CLI子进程 |
| 同 ID 纯换稿 | prompts replace | 一次调用、其他正文保持、纯文本路径不读媒体/账本、并发替换 |
| H3 冻结计划 | plan / batch plan | 有序范围、素材字节、配方哈希、渲染文本、首次/等价计划复用、歧义拒绝 |
| 图片准备/导入/收集 | images prepare / collect | 完整 request/recipe/draft、进度恢复、1.1.0 result、实际回执与文件 |
| 图片计划与规格 | images plan | gpt-image-2.5 / medium / n=1；1920×1088/1088×1920；2K/4K/像素冲突按项阻止 |
| 去噪与模板 | resources / media.denoise | 三类原文 SHA 不变；导入前一次追加；普通/tk 模板分别打包 |
| 图片 JSON / edits | providers/yiciyuang.py | 真本机 HTTP；单 image / 重复 image[]；字节、文件名、MIME与图序 |
| 图片 all-ready / DAG | images/workflow.py | 200 个完整 POST 均先于首个回包；不同图乱序正确关联；依赖登记后即时解锁 |
| 图片有限资源处理 | 显式连接池、预检、流式响应、下载2/解码2/登记1 | 内存/磁盘/句柄预检；真实峰值与等待计时；8 URL 图实测下载峰值2 |
| 图片恢复/一次重试 | recover / resume / retry / restart-of | 401/429/5xx、截断、超时、无自动POST、下载失败不生成、原证据保留 |
| 图片 prepared 恢复协议（PY-03） | images/workflow.py / contracts.py | 完整任务先落盘；同operation幂等预占；五个真实中断边界；双恢复进程；活owner/无主未发送/旧未知；RPM预扣 |
| 图片人工恢复 | attach-result / resolve | 明确文件 SHA、窄范围供应商证据、本地操作不读 Key；期间人工选择保护 |
| 一次视频执行 | video run / execute；batch run | 准备→授权→创建→查询→下载→delivery；8段真HTTP，前4并发、按序补位 |
| 主路径 inline IR | MiniMax-H3 请求 | 真实发送 context_ir_enabled=true；768P/9:16/水印false；差分11个完整payload |
| 视频交付身份 | delivery-v1.json | 新生成、全复用、部分复用；损坏/缺失文件不算交付；损坏项不阻断已受理同伴 |
| 视频单任务与下载 | generate / status --remote / resume / download / attach-task | 原 taskId 恢复；轮询预算；手工关联保留实际终态；缺失文件仅重下 |
| R3 容量 | video/capacity.py | live owner、迟到ID、GET失败释放、POLL_LIMIT保留、issued/applied、终态吸收、恢复5个held |
| 同故事历史观察（PY-01） | 原 video run；共享4路GET | 旧4任务完成仅新增s5；旧任务零下载/零交付；running/预算/错误ID/跨故事隔离；独立调度计数和时序 |
| 历史认证错误恢复（PY-02） | 本轮 created_this_run | 401/402/403保留历史；原未开始项继续；正式一次retry；再次resume零POST；本轮再次拒绝停止新增 |
| 多故事与公平派发 | 持久票据、每批次1–4、同故事提交lease | A优先补位；A限1给B余位；其他故事图片未知不无条件阻断；损坏账本拒绝 |
| 视频一次重试 | batch retry / generate --retry-of | 稳定后继、旧未知保留、A→B作废后A→C；旧授权不重置新绑定；丢job有回执不重建 |
| 限定范围扩大 | batch run --confirm | 只有显式全批确认扩大 retry-only 范围，持久化 full-authorization.json；video run/普通resume不扩大 |
| 独立 IR 支路 | context-ir run/resume/status/attach-task/review/derive | 真独立route/type；无隐式调用；完整响应/文本恢复；语义审核；等价新准备绑定且旧派生计划保持 |
| 文件/锁/崩溃 | persistence/files.py | Windows真进程持锁/杀进程、稳定锁文件、事务中断、替换拒绝重试、路径身份变化 |
| 路径边界 | UNC/设备路径/ADS/保留名/reparse/hardlink | Windows实际 junction、hardlink、大小写与身份变更；不是完整OS目录句柄抗竞争证明 |
| 网络与保密 | HTTPX；credentials/network.py；telemetry | direct/proxy/environment 真HTTP；总deadline；无API重定向/POST重试；媒体无认证头 |
| 凭据 | auth connect / images auth-connect | 真DPAPI假token加密回读/备份；localhost单次token/Host/Origin/时效/体积限制 |
| Skill / 独立安装 | 六正文、三用户入口安装/回滚 | 临时目录发现/引用/用户改动保护；独立venv无Node的3入口CLI假视频 |
| 旧内容迁移 | legacy inspect / import-content | 只读合成旧故事、活跃/unknown拒绝、新projectId/原内容ID、无账本与任务复制 |

## 明确的新协议边界

- 包、故事、配置、环境变量和运行目录使用新命名空间；不读取旧 Key、本机授权或生产状态。旧 v1/历史账本兼容的对应行为是拒绝接管及显式静态内容导入。
- 结构化哈希改为版本化 RFC8785/JCS。旧 localeCompare + JSON.stringify 的哈希不转换或接管。文件和提示词仍按实际字节 SHA-256；数组保持顺序。
- 按当前重建指令，所有创建 POST 都不自动重试，包括旧基线部分分支的“安全429退避重发”。429保存明确结果，下一次生成必须有新的明确一次授权。
- 不提供旧 `--accept-existing-unknown`、旧全局 PID 锁接管、旧 `--runtime-dir` 等绕开新身份的兼容开关。测试运行目录使用独立环境变量，已保存授权还会核对原runtime。旧Node专属 realpath/PID锁重试实现由稳定 OS 锁及Windows有界原子替换取代。
- 独立 IR 的 CLI 明确分成 `context-ir run/review/derive/...`；旧 `plan --from-context-ir` 对应新的 derive。主入口仍只有 inline IR，只有显式审核派生的视频请求使用 false。
- `images prepare` 在同一 Python 进程调用校验器，不提供旧 `--python` 子进程参数。所有新人物/场景/道具配方在哈希前幂等追加原文去噪段；旧 ready 素材和冻结任务不改。
- 本地读取/doctor不自动释放账本。新提交时恢复并核查已登记任务；真实GET失败一次便结束本轮该任务查询并按R3释放，后续显式恢复可重新查询，不隐含远端取消。
- 不承诺逐字台词、音色、审美、供应商真实额度或速度。完整功能离线实现不等于真实生成验收；未观察宿主选择器，不宣称入口已全局启用。
