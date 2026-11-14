# 来源与独立实现

固定参考为 `E:/metasocli`，包版本0.2.0，提交 `f4153c31c63d63c4ead8b2a470dbc5d31ad04d3c`，来源远端 https://github.com/3593297903/metasocli.git 。远端只作来源标识；新项目没有自动设置旧仓库为 origin，没有推送、发布或修改旧目录。

本项目根 `E:/pymetaso`。只从固定提交单向抽取受跟踪的源码、模板、文档和合成测试到 `.baseline`，未复制旧 .git、node_modules、真实素材、凭据、本机授权或生产账本。旧 Node 构建仅发生在本项目 `.baseline` 隔离副本，作为差分和性能参考；wheel/运行时不依赖该目录。

来源清单 [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) 记录254个文件的固定提交、SHA-256、目标和原因；[RESOURCE_MANIFEST.json](RESOURCE_MANIFEST.json) 逐项记录19个资源/helper的源目标哈希和适配理由。三个去噪 TXT 原文字节完全保留；helper单向复制后改成同进程 Python 模块、JCS和 importlib.resources；模板文档改为新 namespace/CLI 引用。包内资源由 wheel smoke 验证，不依赖启动 cwd。

[BASELINE_STATE.json](BASELINE_STATE.json) 保存开工时旧提交、状态与环境记录。用户交接原文保留在 handoff/。最终验收报告另记录收工只读 Git 核对结果。

新项目版本独立，不冒充旧0.2.0；开发期0.1.0a1通过9项完整离线门槛后提升为0.1.0，并对发行版本复验。本地没有创建Git提交；源码交付身份由文件清单/发行文件哈希与版本共同标识，不能把旧提交号说成新代码提交号。

新协议明确不兼容旧授权/结构化哈希/锁文件/活跃任务，不迁移旧运行账本。旧版 pre-IR/v1账本兼容测试在本项目对应“拒绝接管＋静态内容单向导入”，不宣称旧状态格式直接可执行。API业务字段、完整正文、媒体字节和有序引用由差分验证，不笼统忽略所有字段。
