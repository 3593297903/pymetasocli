# 配置、恢复、迁移和 Skill

## 配置与网络

默认配置 `~/.metasocli-py`，默认共享运行目录 `~/.metasocli-py-runtime`；不读取旧变量或旧安装目录。每个供应商使用独立文件 `metaso-network.json` / `images-network.json`：

```json
{"mode":"direct"}
```

显式代理为 `{"mode":"proxy","proxy":"http://127.0.0.1:7890"}`；继承环境为 `{"mode":"environment"}`。缺省 direct，HTTPX trust_env=false，不更改系统代理，也不声称绕过 TUN。TLS验证开启，API不自动重定向/POST重试。下载不携带 API 认证头；校验 public HTTPS、解析 IP 并绑定连接地址，图片不重定向，视频至多3次。测试 loopback 注入只在 Python 接口，CLI/配置/环境没有测试 origin 开关。

Windows auth connect 使用随机单次 token、有效期、Host/Origin 和请求大小校验的短时本机表单。DPAPI 加密、解密回读通过才替换，保留密文备份；失败不破坏旧值。auth status 报告本地配置/可解密、远端认证未测试、真实生成未测试。其他平台使用独立环境变量。

## 恢复命令

| 场景 | 入口 |
|---|---|
| 原批次继续/剩余授权内未开始项目 | batch resume --root … --batch … |
| 原视频查询/下载 | resume / download --root … --operation … |
| 手动关联原 taskId | attach-task --root … --operation … --task … --confirm-task-link |
| 一次视频新尝试 | batch retry --root … --batch … --operation … --confirm；无ID未知另加 --accept-unknown-result |
| 图片原完整响应/URL恢复 | images recover --root … --operation … |
| 图片原授权未开始项目 | images resume --root … --plan … |
| 图片一次新尝试 | images retry --root … --operation … --confirm；未知另加 --accept-unknown-result |
| 图片人工关联 | images attach-result --root … --operation … --file … --expected-sha256 … --confirm-result-link |
| 图片未知供应商证明 | images resolve --root … --operation … --evidence … --outcome failed或not-created --confirm-resolution |
| 已知视频登记到本账本 | batch register --root …（本地，不是远端核实） |
| 独立IR恢复 | context-ir resume --root … --operation … |
| 独立IR人工关联 | context-ir attach-task --root … --operation … --task … --confirm |

不删除账本、receipt 或 unknown 来“解锁”。恢复绑定原输入、原ID和原runtime。损坏文件保留现场；无法证明身份时拒绝新增。用户停止后停止派发，为在途回执最多保留5秒接收窗口；未知保留且不推断远端取消。已开始的线程解码不会被强制终止，线程只处理受限本地字节，不执行生成 POST。

独立 IR：`plan --episode … --workflow h3-context-ir` → `context-ir run --plan … --segment … --confirm` → `context-ir review --operation … --file …` → `context-ir derive --operation …`，每步均传原故事 `--root`。审核包含 schemaVersion=1、operationId、promptHash、verdict、reviewer、dialogueQuotes、有内容的四类 findings（dialogue/references/narration/constraints）。verdict=needs_review可保存但不能派生，approved才能derive。失败/取消后的显式新尝试使用 run --retry-of，未知需先恢复原ID。

等价选段因其他集变化而形成新准备计划时，review/derive可显式带 `--plan <新准备ID>`；核对原文、配方、媒体哈希与顺序一致后复用原IR结果。每个准备绑定保存独立review；已派生计划的review不得覆盖，不额外创建IR。

只授权一个重试的批次保持限定范围，普通video run/批次resume不能顺带提交其他段。之后用户明确授权整个冻结批次时，`batch run --batch … --confirm`保存新的全批授权，再提交原范围内剩余项。全批确认仍不会自动重试失败或unknown任务。

图片run保存 `image-runs/<planId>-index.md`、`<planId>-timing.json` 和必要图齐备后的 `<planId>-video-check.json`。最后一份只做本地H3请求技术检查，不创建视频计划或任务。collect按实际Job和文件哈希产出结果，缺失或损坏文件不伪装完整交付。

## 三个用户入口

六个 Skill 正文随 wheel 打包，也在项目 skills/ 中。临时目录安装/回滚命令：

```text
metasocli-py skills install --user-dir <temporary-skill-directory>
metasocli-py skills uninstall --user-dir <temporary-skill-directory>
```

安装三个新名字：metasocli-py-video-prompts、metasocli-py-video-prompts-旁白、metasoclitk-py。每个入口包含所需同包正文和引用。安装所有目标先检查冲突，不覆盖外来同名文件；回滚核对 owner 与实际文件哈希，有用户改动则保留并报告冲突。

本次只在隔离临时目录测试，没有全局安装，未观察宿主选择器。用户以后明确要求启用时，再使用实际用户 Skill 目录并遵守宿主审批；不能宣称安装文件就已经显示在选择器。

## 旧故事与生产切换

`legacy inspect --source <old-story>` 只读报告；`legacy import-content --source … --root <new-empty-story> --name …` 仅在无活跃/unknown记录、无旧锁时复制内容和经校验媒体。保留集/段/资产 ID，分配新projectId，记录来源哈希；不复制旧运行账本、任务、凭据或授权。

存在旧任务先在旧引擎恢复，不进行跨引擎接管。新旧使用同账号时只能启用一个提交引擎；各自账本不会共享四并发上限，不同 Key 也可能属于同一账号配额。本次所有验证使用合成数据，没有供应商真实验收；正式切换需要之后明确指定范围和次数的真实测试。

Windows AMD64/CPython3.14.5为实际验证平台。Python3.13、Linux、macOS尚未实机验收；跨平台代码路径和条件测试不等于实机证明。MP4结构合成样例不是可播放内容；音视频解码验证另看验收记录。
