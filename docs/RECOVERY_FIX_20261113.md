# 三项恢复修复验收（2026-11-13）

版本保持 **0.1.0**，新项目无 Git 提交号。旧来源 f4153c3 只表示来源。本轮全量 **110 passed / 0 failed / 0 errors / 0 skipped**；原76项有效场景保留。原有 test_*.py 文件逐字节保持，新增核验测试仅删除3个未使用 import。

## 修前与修后

| 缺陷 | 修前实测 | 修后实测 |
|---|---|---|
| PY-01 | 旧4任务 held，新选s5：GET=0、新POST=0、partial | 同入口观察旧ID，必要GET并行，仅新增s5；旧段零下载、不进delivery |
| PY-02 | 历史401使正式后继被PROVIDER_AUTHORIZATION阻止，新POST=0 | 401/402/403分别通过；原未开始项继续；显式retry恰好1 POST；重复resume为0；本轮再次拒绝停止新增 |
| PY-03 | quota先写、job未写中断后唯一名额永久占用，resume POST=0 | 完整prepared先写；前两个边界原授权首次POST=1，意图后/POST中/完整回执后不重复POST |

[修前3 failed](reports/repair-before-authorized.log) · [修后3 passed](reports/repair-three-after.log) · [最终pytest](reports/pytest.xml)

## 修改与必要性

- video/execution.py：统一选段/历史GET持久化、共享4路限制、operation去重及重试祖先去重；本轮created_this_run；已下载文件缺失时恢复原终态结果下载。后两项兼容保护由原有效用例验证。
- video/capacity.py：只读同故事held已知ID候选及冻结身份核验；兼容由创建回执恢复但job尚未写入的迟到ID。没有改R3决策算法、公平票据或限额。
- images/workflow.py：prepared协议证明、原授权关联、持久化顺序、幂等预占、RPM预扣/再入场、两次发送归属核查、无主可证未发送修复与保留孤位诊断。
- images/contracts.py：可选协议字段及严格状态条件校验；新prepared无发送字段，新发送意图必有有限正数epoch及带时区ISO时间。旧记录按原必需发送字段继续读取，不重算其冻结请求。
- tests/fake_http.py 与 process_worker.py：仅供本地故障注入、查询延迟/错误ID/401/402/403、真实子进程和网络封锁；新增3份测试文件。文档/错误码/测试清单/发行哈希同步实际行为。
- 其余生产模块、三个Skill固定入口及其资源、供应商、模型、尺寸、网络路由、超时、凭据实现、提示词/图序/图库、版本号与依赖锁均保持。开发辅助脚本放本次.work目录，未安装全局Skill。

## 新增调度计数与耗时

- 有旧占位：历史GET=4，当前GET=1，新增POST=1，旧段下载=0；GET峰值4；本次运行1211.56 ms，首个旧终态到s5创建174.17 ms。快终态先补位，不等待三个延迟的旧查询；HTTP取消不推断远端终止。
- 无历史阻塞：2 POST / 2当前状态GET / 2下载GET / 0历史GET；804.13 ms。
- 旧running与本地预算耗尽保持held；GET失败按R3释放但保留原ID；错误taskId不会发布终态；活owner保护、跨故事零代查、selected去重、迟到终态和旧未知授权作废均覆盖。
- 图片单项实测：275.65 ms；workflow JSON写入计数{"authorization": 1, "job:prepared": 1, "quotaLedger": 3, "job:submitting": 1, "job:response_saved": 1, "job:received": 1, "job:downloaded": 1, "job:registered": 1}。相对核验源码每项新增prepared job与意图ledger各1次，删除重复run绑定写1次，净增1次。响应流/其他模块回执写不在此计数范围。
- 200图首/末POST：1915.93/46451.89 ms，总计96195.82 ms；旧报告为600.72/12829.54/54498.50 ms。新协议增加必要持久化与证明读取，实际开销如上，未声称无性能代价。200请求仍全部先于第一个响应。
[调度原始计数](reports/repair-scheduler.json) · [无历史正常路径](reports/repair-normal-scheduler.json) · [写入计数](reports/repair-image-writes.json) · [200图](reports/image-200.json) · [换稿/换图及完整11请求差分](PERFORMANCE.md)

## prepared与旧孤位

- 新协议必须有完整job/plan/run/operation/输入哈希/授权哈希/runtime关联；检查正向提交证据。prepared前两边界只接续原operation的首次POST；submitting/unknown只恢复结果。recover命令零POST。
- 预占计入并发；同operation幂等并保留有效RPM窗口。被释放且窗口过期的预占重新入场时扣新窗口，不能绕过RPM。
- 其他故事修复先取得已退出owner的稳定故事锁，再锁外查源，保持该lease直到共享锁内复核原slot/版本/身份并记录释放审计，避免owner重启/退出的竞态；不写对方job或授权。当前run发送前复核持有名额。
- 旧无job/无协议孤位、unknown、损坏回执或requestHash冲突不自动释放；明确返回quotaDiagnostics。缺文件不等于没发。没有新增手动清理命令、第二确认或Codex往返；不能证明未发送的历史记录继续沿用原有未知结果恢复规则。
- 真实子进程分别在prepared后、admission后、意图后、POST中、完整响应后终止；两个恢复进程在concurrent=1下总POST=1、admission=1，再次resume=0。原image-after-intent仍在可能发送边界之后。

## 门槛、保护与限制

- 全部9个原门槛以UV_OFFLINE=1、锁定现有依赖执行：Ruff、Mypy、全pytest、构建、version/help、独立wheel无Node三入口、现有benchmark与11个完整payload差分。原76场景及新场景实际通过；没有skip/xfail或削弱原断言。
- 保留：同ID换图/同集段ID换稿、四并发按序补位、公平票据、一次启动准备生成下载交付、reused、all-ready/DAG、完整回执、未知保护、原子文件与稳定OS锁。
- 零付费调用证据：测试环境清除四个Key变量，仅测试子进程设独立config/runtime；socket外网封锁保留，服务需显式loopback注入，全部请求为合成假服务。真实图片/视频/独立IR调用均为0，未使用真实Key、未推送GitHub。真实供应商接口、余额/额度与媒体质量未验收。
- 开工189个登记文件与快照完全一致；备份、SHA和所有验收命令退出码/日志保存在 `E:\pymetaso\.work\recovery-fix-20261113-2b10f1fa`。旧项目仅只读参考，未访问生产故事/账本/旧Key。新项目没有Git提交。
- 环境问题单列：最初两次沙箱pytest因Windows临时目录访问拒绝失败（3个setup errors/退出异常），随后通过工具正常审批在相同隔离与外网封锁下执行。未修改安全机制、权限或依赖版本。首轮全量107 passed/1 failed的迟到ID兼容失败与所有中间失败日志均保留，未冒充最终成功结果。
- 实测仅Windows AMD64/CPython3.14.5；其他OS/Python版本未实机验收。R3释放只是本地容量决策，不是取消远端。

[门槛命令与退出码](reports/verification.json) · [修复过程命令](reports/repair-commands.json) · [保护与改动哈希](reports/repair-summary.json) · [发行哈希](ARTIFACTS.json)
