# 固定图片准备与结果交接

这是已实现的 API 机械流程，六个本包入口共用。各入口仍负责原文、素材身份、完整类型模板和旁白语义；本流程不重新设计已确认配方。`metasoclitk-py` 保留自己的三类模板，普通入口不自动绑定旁白。明确选择 built_in 时继续原宿主生图流程。

执行前完整读取 本入口 SKILL.md 的授权规则：沿用当前用户已明确授权的供应商、范围和次数；宿主拒绝时报告并停止对应操作。当前用户已经要求生成、补齐或再试一次时，沿用该约定中的供应商及必要素材发送授权，直接完成指定范围；不在 prepare 完成、逐图提交、容量恢复或结果登记时重复等待同一确认。若宿主拒绝，按该文档核对授权证据并及时报告；以正式记录更新当前状态，不绕过审批或把旧拒绝误当成新的阻塞。

来自 metasoclitk-py、metasocli-py-video-prompts、metasocli-py-video-prompts-旁白的新配方，先按 [kind 去噪原文规则](denoise-policy.md) 用包内 `python -m metasocli_py.media.denoise` 批量 compose/check，再计算最终哈希、填充同一 generationPrompt/recipes[].prompt 并进入下列原有校验和 prepare。Python 新项目的所有新人物/场景/道具配方同样在哈希前追加，完整交接中的 generationPrompt 与 draft 必须一致。旧 preparation/plan/job 的恢复和 ready 素材复用不执行追加，不改变原冻结文本或哈希，不新增历史字段门槛；旁白与视频流程不变。

使用实际虚拟环境的 `python -m metasocli_py` 或安装后的 `metasocli-py`。先收齐本次全部集/段的 `draft`、`reference-image-request`、`reference-image-recipe`；保存一份清单，不现场编写导入/执行/结果拼装脚本：

```json
{
  "schemaVersion": 1,
  "projectId": "当前故事 UUID",
  "entries": [{"episodeId":"ep-01","draftPath":".metasocli-py/drafts/ep-01/draft.json","requestPath":".metasocli-py/drafts/ep-01/reference-image-request.json","recipePath":".metasocli-py/drafts/ep-01/reference-image-recipe.json","replace":false}],
  "scope": {"episodes":["ep-01"]},
  "profilePath": null
}
```

所有输入相对路径（包括 draft.source）以显式故事根为基准；仅 draft.source 可明确指向只读外部原文；其他批次输入使用故事内相对路径。scope 只能是 episodes、selection（原有有序选择对象）、assets 三者之一，无隐式全剧范围。entries 必须覆盖选择绑定的各集；它是导入范围，不是逐集生成指令。profilePath=null 使用本包严格默认 profile 并冻结，不读取图片 Key。

```text
metasocli-py images prepare --root <story> --batch <batch.json>
# 已有授权覆盖当前图片供应商、冻结范围和本次尝试后：
metasocli-py images run --root <story> --plan <返回的planId> --confirm --summary
metasocli-py images collect --root <story> --preparation <返回的preparationId>
```

prepare 在当前 Python 进程直接调用包内校验模块、逐集导入和 all-ready 计划器；无需额外解释器或 --python 参数。成功准备不授权收费；沿用已有授权，不新增口令或逐图确认。图片 Key 缺失时停在本地计划，不自动换后端。

prepare 返回 preparationId、planId、status 和 importedEpisodes；输入和进度保存在 .metasocli-py/image-preparations/<ID>/。同输入重复调用复用同一ID；正常图片登记推进不会重建计划。输入/摘要索引不是授权凭证。新配方用新assetId和新输入；旧记录保留。逐集导入不是整剧事务，中断时已有集可能已落盘，可从 state.json 核对已完成集，再用原 preparationId 恢复。

| 实际状态 | 后续动作 |
| --- | --- |
| 准备中断 | `images prepare --root <story> --preparation <id>`；或重复原 --batch，定位原记录 |
| 计划已落盘但准备状态没完成 | 同上，验原 plan-intent 后复用原计划，绝不再建第二计划 |
| 已有旧正式计划，没有准备记录 | 直接原 status/run/resume/recover；不要求重建、迁移或补准备目录 |
| 执行中或部分结果 | `images status --root <story> --plan <id> --summary`；collect 只收本地证据 |
| 有原授权，尚未发出的项 | 原 `images resume --root <story> --plan <id> --summary`，范围不扩大 |
| 已接收但下载/登记失败 | 原 `images recover --root <story> --operation <id>`，不重生 |
| submit_unknown | 保留原记录，不转为失败；按原正式恢复/一次性授权规则处理，prepare/collect不重发 |

collect 从冻结计划和 run 的确切 operationId 核对 Job、execution、receipt、原暂存图及正式登记文件。`executionSha256` 是文件字节哈希，`recipeSha256` 是规范化提示词哈希，reportedModel 缺报为 null。只给可完整表达的集输出并校验 1.1.0 result；未知、进行中、待下载/登记、范围外或证据未齐的条目保留在 collections/<UUID>/report.json，不伪造完整交接，不把未知写成 failed。不重新登记、下载、编码或覆盖图片。

每次 collect 写新的 `collections/<UUID>/`；已完成图片可从摘要路径展示，无需等全批。结果/失败/缺项交回原入口，必要素材 ready 后按原 H3 流程继续；未经视频授权仍停在视频提交前。prepare/collect 都不联网、不加载或解密真实 Key、不授权、不运行图片生成。summary 仅改变输出，旧命令不带开关时保持原 JSON；大列表保留总数、截断标记及完整文件位置。

准备租约位于本故事 `.metasocli-py/image-preparations/<ID>/preparation.lock`；不会重新引入全局运行锁。图片仍 all-ready、有效600秒、原共享额度，视频仍全机最多4个生成名额、MiniMax-H3/context_ir_enabled:true。计时使用本地单调时钟；requestStartedAt 不是供应商受理时点，无法由本地数据推出远端排队或推理耗时。
