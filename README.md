# metasocli-py

独立 Python 故事、图片与 Metaso MiniMax-H3 CLI。运行时不依赖 Node、旧 metasocli 源码或旧配置。版本 `0.1.0`；完整离线验收结果见 [验收记录](docs/ACCEPTANCE.md)，发行文件与源码哈希见 [ARTIFACTS.json](docs/ARTIFACTS.json)。

## 本地安装和验证

支持标准 CPython `>=3.13,<3.15`；本机使用 `C:\Python314\python.exe`（3.14.5，Windows AMD64）。

```powershell
uv sync --locked --link-mode copy
uv run --locked --no-sync ruff check .
uv run --locked --no-sync mypy src/metasocli_py
uv run --locked --no-sync python -m pytest
uv build
.venv\Scripts\python.exe -m metasocli_py --version
.venv\Scripts\python.exe -m metasocli_py --help
uv run --locked --no-sync python scripts/package_smoke.py
uv run --locked --no-sync python scripts/benchmark.py
```

日常运行直接使用项目 `.venv\Scripts\python.exe -m metasocli_py` 或安装后的 `metasocli-py`；不必再次同步依赖。其他平台的虚拟环境解释器位于 `.venv/bin/python`。独立安装使用 `uv pip install --python <venv-python> <wheel>`；生产无需开发依赖。锁定依赖导出可用 `uv export --locked --no-dev --no-editable --no-emit-project`。

完整复验脚本为 `scripts/verify.py`；只访问合成数据和显式注入的本机假 HTTP 服务。测试默认阻止外网。首次依赖准备需要正常网络和宿主授权，不涉及供应商业务请求。

```powershell
uv run --locked --no-sync python scripts/verify.py
```

所有执行指令原文已保存在 [docs/handoff](docs/handoff)。输入样例和严格schema见 [输入格式](docs/INPUT_FORMAT.md)，实际解析器帮助见 [CLI参考](docs/CLI_REFERENCE.md)。

## 故事与固定入口

每个新故事使用独立空目录，所有命令传明确 `--root`。清单为 `metasocli-py.yaml`，状态目录为 `.metasocli-py`。

```text
metasocli-py init --root <new-story> --name <name>
metasocli-py import --root <story> --draft <draft.json>
metasocli-py assets register --root <story> --id <asset-id> --file <image-or-audio>
metasocli-py prompts replace --root <story> --episode ep-1 --segment s1 --file <complete-prompt.txt>
metasocli-py video run --root <story> --episodes ep-1,ep-2
```

最后一条没有 `--confirm` 时只冻结并报告本地计划。用户已明确授权对应供应商、范围和次数后，添加 `--confirm` 可在一次调用中完成准备、创建、轮询、下载与 delivery。不要在本次离线开发验收中执行真实生成。

部分段选择文件：

```json
{"schemaVersion":1,"episodes":[{"episodeId":"ep-1","segmentIds":["s1","s3"]}]}
```

使用 `--selection <file>` 替代 `--episodes`。返回的 batchId 可用于 `batch resume --root <story> --batch <id>`；已有 taskId 的恢复和下载不生成新任务。更换正文或图片后准备新计划；已受理任务始终按原 taskId 恢复。

三个成品入口分别为普通 `metasocli-py-video-prompts`、旁白 `metasocli-py-video-prompts-旁白`、tk `metasoclitk-py`，均使用相同换图、换稿、video run 入口。旁白需单独登记合法 MP3/WAV，明确 narration.assetId 和 UTF-16 cues；普通入口不自动绑定旁白。tk 使用包内独立人物/场景/道具模板。

## 图片与配置

`images prepare --batch <batch.json>` 校验完整 request/recipe/draft 并导入全部指定内容；`images plan` 冻结配方；`images run --plan <id> --confirm` 执行授权范围；`images collect --preparation <id>` 从回执收尾。完整契约和示例在包内参考图片 Skill 中：

```text
metasocli-py skills read metasocli-py-reference-images
metasocli-py skills list
```

图片默认 gpt-image-2.5、medium、n=1、URL 回包（兼容 Base64）；all-ready，每项一个请求，下载/解码各2、登记1。默认总等待600秒，上限1200秒，显式 exact=300秒保留。人物/场景/道具1920×1088，首帧1088×1920。完整类型去噪原文在配方哈希之前幂等追加一次。

独立变量为 `METASOCLI_PY_METASO_API_KEY` 和 `METASOCLI_PY_IMAGE_API_KEY`；不读取旧变量。Windows 可用 `auth connect` / `images auth-connect` 通过短时本机表单加密保存。不要把真实 Key 写进命令行、聊天、项目或报告。配置目录默认 `~/.metasocli-py`，运行账本默认 `~/.metasocli-py-runtime`；测试分别用 `METASOCLI_PY_CONFIG_DIR` / `METASOCLI_PY_RUNTIME_DIR` 指向隔离目录。

网络模式、恢复、安装与迁移详见 [运行说明](docs/OPERATIONS.md)；严格输入、哈希、状态约定见 [行为契约](docs/BEHAVIOR_CONTRACT.md)。来源和旧测试映射见 [固定基线](docs/SOURCE_BASELINE.md)、[功能矩阵](docs/FEATURE_MATRIX.md)。

逐文件测试对照见 [SOURCE_TEST_MAP](docs/SOURCE_TEST_MAP.md)，错误定位见 [ERROR_CODES](docs/ERROR_CODES.md)，冷/热调用与200图片内存指标见 [性能报告](docs/PERFORMANCE.md)。完整证据由验收脚本保存在 `.work/reports/`，交付副本位于 `docs/reports/`。

本次不安装全局入口，不推送 GitHub，不调用真实付费服务。同账号正式切换时仅启用一个提交引擎：新旧账本不会自动合并，两个 Key 也可能共享账号配额。
