# 行为契约

## 输入、文本与哈希

- 严格 Pydantic 契约拒绝多余字段和类型转换。JSON/YAML 拒绝重复键、非法数、非法 Unicode；YAML 拒绝 anchor、alias、非 JSON 隐式类型。布尔值不是整数，taskId 始终是有界字符串。
- 来源只去首 BOM，将 CRLF/CR 规范为 LF；保留空白和末尾换行，不做 Unicode 规范化。source 和 narration cues 均使用 UTF-16 code units；拒绝切开 surrogate pair，分段连续覆盖来源。
- draft: episodeId、kind（script/video-prompts）、source、offsetEncoding=utf16、segments、recipes。segment 的 start/end 指向来源；成品 prompt 必须等于来源片段；剧本增强 prompt 必须保留该来源全文。源原始字节和规范文本分别保存哈希。
- 视频可执行时长为4–15秒，小数向上取整；原目标写入 targetDurationSeconds。H3 渲染后最多7000个 Unicode 码点、九张有序参考图；首帧仅一张，不能与普通参考图或旁白混合。最多一个旁白音频。
- 文件/正文哈希按实际字节 SHA-256。新结构化记录使用 RFC8785/JCS + SHA-256，标注 hashVersion=jcs-sha256-v1；排除对应自哈希字段，数组不重排。不接管旧 canonical 哈希或授权。

## 本地修改与事务

换图沿用 assetId，只改选中 media 和 revision；配方、正文、引用和图库不改。换稿沿用集段 ID，保留时长、资产、其他正文和图序，仅维护必要偏移。旁白 cue 只有唯一文本匹配才能自动重定位，有歧义拒绝。两者一次 CLI 返回；纯换稿不读取媒体字节或容量账本。

多文件事务先保存变更日志及 staged bytes，清单最后发布；崩溃后滚动恢复。单文件临时写、fsync、os.replace；Windows 拒绝替换时有界重试，绝不先删旧文件。OS 锁文件稳定保留，实际持锁判断独立于业务状态。短 Story/账本锁内不等待 HTTP、Pillow 或用户输入。修改在锁内重新核对版本/哈希，避免锁外旧读覆盖新内容。

## 图片

准备、计划、执行、收集职责分离。准备过程持久化输入、每集导入进度和计划意图；恢复重用同一 preparation/plan 身份。all-ready 依赖完成正式登记即解锁。输入冻结完整 prompt、配方、依赖顺序/字节哈希、目标当前哈希和 profile；参考图以实际生产者结果绑定。

状态链：prepared → submitting → response_saved → received → downloaded → registered；明确拒绝为 rejected，无法证实是否受理为 submit_unknown。完整 prepared 先落盘，再原子获取或接续同 operation 的并发/RPM 预占，然后持久化 submitting 意图，最后 POST。响应流式写入，完整性证明与正文哈希匹配后才解析。JSON generations；有参考图 multipart edits（单图 image，多图重复 image[]）。无自动 POST 重试。

新记录使用 `submissionProtocol=prepared-before-admission-v1`，prepared 必须具有完整冻结输入、原授权哈希与 preparedAt，且没有发送时间或结果证据；submitting 及之后必须保留 sentEpoch/requestStartedAt。恢复校验 job/plan/run/operation/输入哈希和原 runtime。只有可证明未发送的 prepared 才由原 run/resume 接续首次 POST；recover 本身仍为零 POST。旧格式记录继续按原必需发送字段读取，无协议的 prepared 不被当作可重发证明。

预占计入并发，RPM 在 admission 时预扣，同 operation 接续不重复扣减或重置有效窗口。活 owner 不释放。其他故事的退出 owner 只有在取得其稳定故事锁、锁外读到完整未发送证明，再于共享锁内复核原 slot 版本和身份后才能释放预占；保留审计和原 job/授权。原故事恢复已释放预占时重新走限额。发送意图前和 POST 前检查名额归属。旧无 job/无协议孤位、损坏回执、冲突身份继续保留，返回 quotaDiagnostics；文件缺失不是未发送证据。

URL 下载失败、解析/登记中断优先恢复同一完整响应；未知保留证据。正式一次重试持久关联 retryOf，不能通过换 plan 绕过同故事未知。人工结果关联需要明确确认和预期文件哈希；不能覆盖期间新增的用户选择。resolve 仅处理未知，记录供应商证据；支持窄范围独立验证的已保存 API 拒绝/终止响应，其他外部证明标注用户报告。

## 视频与容量

主入口只有一次内联 IR 视频创建，context_ir_enabled=true。创建120秒、查询30秒；默认轮询60次/5秒，下载并发2。先保存授权范围和提交意图，再 POST；完整创建回执早于 queued 更新。已受理快照不随故事变更改写。

R3 共享账本最多给新增任务四个 held 名额，批次上限1–4。按进入顺序给仍有待提交项的批次优先补位，余位可供其他故事。可信终态立即释放，下载不占生成名额。

原 run 在存在待派发项时观察同故事未选中的 held 已知 taskId，校验旧任务自身父计划与身份；与当前选段去重并共享最多4路 GET。沿用调用者已有轮询次数、间隔和容量等待预算，终态立即唤醒补位。观察仅更新任务状态/R3，不生成、不下载、不加入当前 delivery，不查询其他故事。保护 operation owner；当前 run 自持的 submission.lock 不代表历史 operation 仍活跃。

401/402/403 仅在本次调用实际新派发的创建尝试中停止后续派发。历史错误保留；修正凭据/余额后，原授权未开始项可继续，失败段仍需正式一次 retry。重复 resume 不消费新 POST，也不增加 Key 验证网络调用。

| 证据 | 本地容量 |
|---|---|
| 无 taskId、提交 owner 仍持锁 | held |
| 无 taskId、创建结束/owner退出 | released，未知保留 |
| GET失败/身份无法确认/来源证据失效 | released，原ID与证据保留 |
| queued/running，仅轮询预算耗尽 | held |
| 匹配可信终态 | released，迟到活跃事件不可复活 |
| 更新的匹配活跃证据 | 恢复held，超过4则停止新增 |

issued/applied 观察序号、终态事件、lastRelease/lastRestore、迟到 ID 修复都持久保存。释放本地容量不等于取消远端，不能保证远端绝对四并发。status/doctor 不清容量；已授权 run 绑定原 runtime，不能换目录恢复以重置名额。

相同旧损坏来源不能覆盖其后已接受的活跃观察；来源内容或不可读错误的指纹改变才形成新的来源失效证据。已保存受理任务若缺少对应slot，会先按原身份登记再派发。释放后的其他集段/其他输入不再无条件封锁本故事，但同一集段同一输入仍绑定原未知，不能换plan重发。

新尝试保存稳定 operationId、retryOf 和一次授权；unknown 没有 taskId 也可在明确接受未知风险后授权一次。旧未知授权在原 ID 恢复后失效，不可自动变成已知失败重试。receipt/intent 仍存在而 job 丢失时拒绝重建并重发。

本次新生成 reused=false；启动时已验证成片才是 reused=true；混合结果逐项标注。默认 MP4 校验只证明结构、时长、尺寸和字节身份，不能冒充实际解码、音频或视觉验收。--verify-av 可显式调用已安装的 ffprobe/ffmpeg 做音视频流和解码检查。

独立 context-ir 为显式兼容支路，须单独确认；其结果经带哈希的人工语义审核后派生视频计划，派生视频另行确认。普通 video run 不调用独立 IR。
