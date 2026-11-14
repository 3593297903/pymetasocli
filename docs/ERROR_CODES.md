# 错误码索引

由当前源码的字面量错误码生成；动态包装的底层I/O错误归入 LOCAL_INPUT_OR_IO/LOCAL_IO。错误不会回显 Key、原始响应、完整签名URL或Pydantic输入。

CLI：0为当前操作成功，1为输入/身份/本地错误，2为部分交付/待恢复/停止。部分结果内逐项error应结合状态读取，不能把unknown当失败。

| 错误码 | 实现位置 |
|---|---|
| `API_KEY_MISSING` | `src/metasocli_py/credentials/config.py:71`, `src/metasocli_py/providers/metaso.py:37` |
| `API_ORIGIN` | `src/metasocli_py/providers/http.py:73` |
| `ASSET_CHANGED` | `src/metasocli_py/application/assets.py:25`, `src/metasocli_py/video/planning.py:95` |
| `ASSET_ROLE` | `src/metasocli_py/application/assets.py:20`, `src/metasocli_py/application/story.py:107` |
| `AUDIO_DURATION` | `src/metasocli_py/media/inspect.py:45` |
| `AUDIO_INVALID` | `src/metasocli_py/media/inspect.py:43`, `src/metasocli_py/media/inspect.py:51`, `src/metasocli_py/media/inspect.py:86` |
| `AUDIO_LIMIT` | `src/metasocli_py/media/inspect.py:39` |
| `AUTHORIZATION_IDENTITY` | `src/metasocli_py/images/workflow.py:637`, `src/metasocli_py/video/execution.py:351`, `src/metasocli_py/video/execution.py:353`, `src/metasocli_py/video/execution.py:386`, `src/metasocli_py/video/execution.py:396` |
| `AUTHORIZATION_REQUIRED` | `src/metasocli_py/cli.py:314`, `src/metasocli_py/cli.py:362`, `src/metasocli_py/images/recovery.py:29`, `src/metasocli_py/images/workflow.py:641`, `src/metasocli_py/video/context_ir.py:86`, `src/metasocli_py/video/execution.py:367`, `src/metasocli_py/video/retry.py:14` |
| `CAPACITY_EVENT` | `src/metasocli_py/video/capacity.py:26` |
| `CAPACITY_IDENTITY` | `src/metasocli_py/video/capacity.py:107`, `src/metasocli_py/video/capacity.py:132`, `src/metasocli_py/video/capacity.py:154`, `src/metasocli_py/video/capacity.py:158`, `src/metasocli_py/video/capacity.py:24`, `src/metasocli_py/video/capacity.py:251`, `src/metasocli_py/video/capacity.py:260`, `src/metasocli_py/video/capacity.py:30`, `src/metasocli_py/video/capacity.py:33`, `src/metasocli_py/video/capacity.py:88` |
| `CAPACITY_MISSING` | `src/metasocli_py/video/capacity.py:219` |
| `CLI_ARGUMENT` | `src/metasocli_py/cli.py:31`, `src/metasocli_py/cli.py:380` |
| `CONFIGURATION_REQUIRED` | `src/metasocli_py/video/execution.py:369` |
| `CONTENT_CHANGED` | `src/metasocli_py/application/story.py:203`, `src/metasocli_py/application/story.py:43`, `src/metasocli_py/video/planning.py:155`, `src/metasocli_py/video/planning.py:77` |
| `CREATE_CONTRACT` | `src/metasocli_py/providers/metaso.py:20`, `src/metasocli_py/providers/metaso.py:23`, `src/metasocli_py/providers/metaso.py:27`, `src/metasocli_py/providers/metaso.py:30` |
| `CREDENTIAL_ENCRYPTION` | `src/metasocli_py/credentials/config.py:40` |
| `CREDENTIAL_INVALID` | `src/metasocli_py/credentials/config.py:49`, `src/metasocli_py/credentials/config.py:67`, `src/metasocli_py/credentials/config.py:74`, `src/metasocli_py/credentials/config.py:78` |
| `CREDENTIAL_PLATFORM` | `src/metasocli_py/credentials/config.py:25` |
| `CREDENTIAL_VERIFY` | `src/metasocli_py/credentials/config.py:53` |
| `DENOISE_INVALID` | `src/metasocli_py/resources/__init__.py:10` |
| `DIALOGUE_CHANGED` | `src/metasocli_py/application/story.py:128` |
| `DOWNLOAD_FAILED` | `src/metasocli_py/providers/http.py:150`, `src/metasocli_py/providers/http.py:152` |
| `DOWNLOAD_REDIRECT` | `src/metasocli_py/providers/http.py:146` |
| `DUPLICATE_FIELD` | `src/metasocli_py/persistence/codec.py:58` |
| `DUPLICATE_REFERENCE` | `src/metasocli_py/application/story.py:101` |
| `DURATION_TARGET` | `src/metasocli_py/domain/text.py:64` |
| `EPISODE_EXISTS` | `src/metasocli_py/application/story.py:146` |
| `EPISODE_MISSING` | `src/metasocli_py/application/story.py:190`, `src/metasocli_py/video/planning.py:39` |
| `EXPECT_SCOPE_REQUIRED` | `src/metasocli_py/cli.py:274` |
| `FILE_CHANGED` | `src/metasocli_py/persistence/files.py:77` |
| `FILE_IDENTITY_UNAVAILABLE` | `src/metasocli_py/persistence/files.py:57` |
| `FILE_LIMIT` | `src/metasocli_py/persistence/codec.py:94`, `src/metasocli_py/persistence/files.py:123`, `src/metasocli_py/persistence/files.py:69` |
| `H3_MODE` | `src/metasocli_py/application/story.py:109`, `src/metasocli_py/domain/text.py:76` |
| `H3_RATIO` | `src/metasocli_py/video/planning.py:107` |
| `HASH_INPUT` | `src/metasocli_py/persistence/codec.py:45` |
| `IMAGE_BATCH_LIMIT` | `src/metasocli_py/images/workflow.py:665` |
| `IMAGE_COLLECTION_CHANGED` | `src/metasocli_py/images/collection.py:83` |
| `IMAGE_COLLECTION_EVIDENCE` | `src/metasocli_py/images/collection.py:45`, `src/metasocli_py/images/collection.py:59`, `src/metasocli_py/images/collection.py:64` |
| `IMAGE_DEPENDENCY` | `src/metasocli_py/images/workflow.py:329`, `src/metasocli_py/images/workflow.py:763` |
| `IMAGE_DEPENDENCY_CHANGED` | `src/metasocli_py/application/assets.py:40` |
| `IMAGE_DIMENSIONS` | `src/metasocli_py/images/workflow.py:592`, `src/metasocli_py/media/inspect.py:28` |
| `IMAGE_HANDOFF_CONFLICT` | `src/metasocli_py/images/workflow.py:110`, `src/metasocli_py/images/workflow.py:118`, `src/metasocli_py/images/workflow.py:253`, `src/metasocli_py/images/workflow.py:94` |
| `IMAGE_HTTP` | `src/metasocli_py/images/workflow.py:548` |
| `IMAGE_INPUT_CHANGED` | `src/metasocli_py/images/workflow.py:334`, `src/metasocli_py/images/workflow.py:766`, `src/metasocli_py/providers/yiciyuang.py:24`, `src/metasocli_py/providers/yiciyuang.py:34` |
| `IMAGE_INVALID` | `src/metasocli_py/media/inspect.py:26`, `src/metasocli_py/media/inspect.py:33` |
| `IMAGE_JOB_IDENTITY` | `src/metasocli_py/images/workflow.py:73`, `src/metasocli_py/images/workflow.py:78`, `src/metasocli_py/images/workflow.py:855` |
| `IMAGE_JOB_MISSING` | `src/metasocli_py/images/workflow.py:755`, `src/metasocli_py/images/workflow.py:865` |
| `IMAGE_KEY_INVALID` | `src/metasocli_py/providers/yiciyuang.py:14` |
| `IMAGE_LEDGER_CONFLICT` | `src/metasocli_py/images/workflow.py:405`, `src/metasocli_py/images/workflow.py:408`, `src/metasocli_py/images/workflow.py:453` |
| `IMAGE_LEDGER_MISSING` | `src/metasocli_py/images/workflow.py:385` |
| `IMAGE_LEDGER_OWNER` | `src/metasocli_py/images/workflow.py:387` |
| `IMAGE_LIMIT` | `src/metasocli_py/images/workflow.py:569`, `src/metasocli_py/media/inspect.py:20` |
| `IMAGE_PLAN_IDENTITY` | `src/metasocli_py/images/workflow.py:216` |
| `IMAGE_PLAN_STALE` | `src/metasocli_py/application/assets.py:36`, `src/metasocli_py/images/workflow.py:314`, `src/metasocli_py/images/workflow.py:331` |
| `IMAGE_PREPARATION` | `src/metasocli_py/images/workflow.py:231`, `src/metasocli_py/images/workflow.py:237`, `src/metasocli_py/images/workflow.py:240` |
| `IMAGE_PREPARATION_BLOCKED` | `src/metasocli_py/images/workflow.py:112` |
| `IMAGE_PREPARATION_STALE` | `src/metasocli_py/application/story.py:175`, `src/metasocli_py/images/workflow.py:116`, `src/metasocli_py/images/workflow.py:285`, `src/metasocli_py/images/workflow.py:90` |
| `IMAGE_PREPARED_IDENTITY` | `src/metasocli_py/images/workflow.py:361`, `src/metasocli_py/images/workflow.py:367`, `src/metasocli_py/images/workflow.py:770` |
| `IMAGE_PROFILE` | `src/metasocli_py/images/workflow.py:54` |
| `IMAGE_QUOTA_HELD` | `src/metasocli_py/images/workflow.py:470` |
| `IMAGE_QUOTA_OWNER` | `src/metasocli_py/images/workflow.py:447`, `src/metasocli_py/images/workflow.py:505`, `src/metasocli_py/images/workflow.py:508`, `src/metasocli_py/images/workflow.py:519`, `src/metasocli_py/images/workflow.py:523` |
| `IMAGE_RECEIPT_IDENTITY` | `src/metasocli_py/images/workflow.py:545` |
| `IMAGE_RESOURCE_LIMIT` | `src/metasocli_py/images/resources.py:23`, `src/metasocli_py/images/resources.py:30`, `src/metasocli_py/images/resources.py:36`, `src/metasocli_py/images/resources.py:39` |
| `IMAGE_RESPONSE_CONTRACT` | `src/metasocli_py/images/workflow.py:554`, `src/metasocli_py/images/workflow.py:557`, `src/metasocli_py/images/workflow.py:559`, `src/metasocli_py/images/workflow.py:567`, `src/metasocli_py/images/workflow.py:573` |
| `IMAGE_RESTART_RECOVERY_REQUIRED` | `src/metasocli_py/images/workflow.py:654` |
| `IMAGE_RESULT_CHANGED` | `src/metasocli_py/images/recovery.py:42`, `src/metasocli_py/images/workflow.py:860` |
| `IMAGE_RPM_LIMIT` | `src/metasocli_py/images/workflow.py:475` |
| `IMAGE_SCOPE` | `src/metasocli_py/images/workflow.py:153` |
| `IMAGE_SPECIFICATION` | `src/metasocli_py/images/workflow.py:194` |
| `IMAGE_SUBMISSION_EVIDENCE` | `src/metasocli_py/images/workflow.py:369`, `src/metasocli_py/images/workflow.py:461`, `src/metasocli_py/images/workflow.py:533` |
| `IMAGE_SUPERSEDED` | `src/metasocli_py/application/assets.py:43`, `src/metasocli_py/images/workflow.py:317`, `src/metasocli_py/images/workflow.py:683` |
| `INLINE_IR_REQUIRED` | `src/metasocli_py/video/execution.py:371` |
| `INTEGER_RANGE` | `src/metasocli_py/persistence/codec.py:26` |
| `INVALID_INPUT` | `src/metasocli_py/cli.py:226`, `src/metasocli_py/cli.py:286`, `src/metasocli_py/cli.py:311`, `src/metasocli_py/cli.py:322`, `src/metasocli_py/cli.py:345`, `src/metasocli_py/cli.py:369`, `src/metasocli_py/contracts/story.py:166`, `src/metasocli_py/images/workflow.py:223`, `src/metasocli_py/images/workflow.py:628`, `src/metasocli_py/persistence/codec.py:115`, `src/metasocli_py/persistence/codec.py:32`, `src/metasocli_py/video/context_ir.py:144`, `src/metasocli_py/video/context_ir.py:82`, `src/metasocli_py/video/planning.py:125` |
| `INVALID_MANIFEST` | `src/metasocli_py/application/story.py:40` |
| `INVALID_NUMBER` | `src/metasocli_py/persistence/codec.py:111`, `src/metasocli_py/persistence/codec.py:28` |
| `INVALID_RECORD` | `src/metasocli_py/persistence/files.py:130` |
| `INVALID_SELECTION` | `src/metasocli_py/cli.py:265`, `src/metasocli_py/video/planning.py:23`, `src/metasocli_py/video/planning.py:28`, `src/metasocli_py/video/planning.py:34`, `src/metasocli_py/video/planning.py:42` |
| `INVALID_UNICODE` | `src/metasocli_py/domain/text.py:13` |
| `INVALID_UTF8` | `src/metasocli_py/domain/text.py:21` |
| `IR_DIALOGUE` | `src/metasocli_py/video/context_ir.py:52`, `src/metasocli_py/video/context_ir.py:57` |
| `IR_JOB_IDENTITY` | `src/metasocli_py/video/context_ir.py:24`, `src/metasocli_py/video/context_ir.py:26` |
| `IR_MODE_CONFLICT` | `src/metasocli_py/video/context_ir.py:89` |
| `IR_NOT_READY` | `src/metasocli_py/video/context_ir.py:212` |
| `IR_PROVENANCE` | `src/metasocli_py/video/context_ir.py:217` |
| `IR_QUERY_CONTRACT` | `src/metasocli_py/providers/metaso.py:80`, `src/metasocli_py/providers/metaso.py:91` |
| `IR_RECEIPT_IDENTITY` | `src/metasocli_py/video/context_ir.py:155` |
| `IR_REFERENCE` | `src/metasocli_py/video/context_ir.py:62`, `src/metasocli_py/video/context_ir.py:65`, `src/metasocli_py/video/context_ir.py:67` |
| `IR_RESULT_IDENTITY` | `src/metasocli_py/video/context_ir.py:180`, `src/metasocli_py/video/context_ir.py:29` |
| `IR_RETRY_NOT_ALLOWED` | `src/metasocli_py/video/context_ir.py:108` |
| `IR_REVIEW` | `src/metasocli_py/video/context_ir.py:227`, `src/metasocli_py/video/context_ir.py:231`, `src/metasocli_py/video/context_ir.py:239`, `src/metasocli_py/video/context_ir.py:39`, `src/metasocli_py/video/context_ir.py:41`, `src/metasocli_py/video/context_ir.py:43`, `src/metasocli_py/video/context_ir.py:47`, `src/metasocli_py/video/planning.py:196`, `src/metasocli_py/video/planning.py:199` |
| `IR_TASK_LINK_REQUIRED` | `src/metasocli_py/video/context_ir.py:167` |
| `IR_TEXT_CHANGED` | `src/metasocli_py/video/context_ir.py:183`, `src/metasocli_py/video/context_ir.py:221` |
| `IR_TEXT_LIMIT` | `src/metasocli_py/video/context_ir.py:36`, `src/metasocli_py/video/planning.py:83` |
| `IR_UNRESOLVED` | `src/metasocli_py/video/context_ir.py:111` |
| `JOB_IDENTITY` | `src/metasocli_py/video/execution.py:409`, `src/metasocli_py/video/store.py:28`, `src/metasocli_py/video/store.py:34`, `src/metasocli_py/video/store.py:36` |
| `JOB_STALE` | `src/metasocli_py/video/store.py:18` |
| `LEDGER_CORRUPT` | `src/metasocli_py/images/workflow.py:390`, `src/metasocli_py/video/capacity.py:76`, `src/metasocli_py/video/capacity.py:79` |
| `LEDGER_MISSING` | `src/metasocli_py/video/capacity.py:68` |
| `LEDGER_OWNER` | `src/metasocli_py/video/capacity.py:71` |
| `LEGACY_ACTIVE` | `src/metasocli_py/application/legacy.py:45` |
| `LEGACY_CHANGED` | `src/metasocli_py/application/legacy.py:54`, `src/metasocli_py/application/legacy.py:65`, `src/metasocli_py/application/legacy.py:71` |
| `LEGACY_FORMAT` | `src/metasocli_py/application/legacy.py:16` |
| `LEGACY_OVERLAP` | `src/metasocli_py/application/legacy.py:42` |
| `LEGACY_REFERENCE` | `src/metasocli_py/domain/text.py:100` |
| `LEGACY_ROOT` | `src/metasocli_py/application/story.py:52`, `src/metasocli_py/application/story.py:57` |
| `LOCAL_INPUT_OR_IO` | `src/metasocli_py/cli.py:404` |
| `LOCK_BUSY` | `src/metasocli_py/persistence/files.py:149` |
| `LOCK_IDENTITY` | `src/metasocli_py/persistence/files.py:152` |
| `MISSING_ASSET` | `src/metasocli_py/video/planning.py:56` |
| `MISSING_RECIPE` | `src/metasocli_py/application/assets.py:17`, `src/metasocli_py/application/story.py:105`, `src/metasocli_py/application/story.py:112`, `src/metasocli_py/images/workflow.py:145` |
| `NARRATION_CUE` | `src/metasocli_py/domain/text.py:80` |
| `NARRATION_REMAP_REQUIRED` | `src/metasocli_py/application/story.py:213`, `src/metasocli_py/application/story.py:216`, `src/metasocli_py/application/story.py:225` |
| `NETWORK_CONFIG` | `src/metasocli_py/credentials/network.py:29`, `src/metasocli_py/providers/http.py:56` |
| `NOT_INITIALIZED` | `src/metasocli_py/application/story.py:35` |
| `OPERATION_EXISTS` | `src/metasocli_py/video/capacity.py:195` |
| `OUTPUT_CHANGED` | `src/metasocli_py/video/execution.py:104`, `src/metasocli_py/video/execution.py:97` |
| `OUTPUT_CONFLICT` | `src/metasocli_py/video/execution.py:144`, `src/metasocli_py/video/execution.py:90` |
| `OUTPUT_NEEDS_RECOVERY` | `src/metasocli_py/video/execution.py:326` |
| `OUTPUT_RECEIPT_MISSING` | `src/metasocli_py/video/execution.py:86` |
| `PATH_ESCAPE` | `src/metasocli_py/persistence/files.py:48`, `src/metasocli_py/persistence/files.py:51` |
| `PATH_UNSAFE` | `src/metasocli_py/persistence/files.py:24`, `src/metasocli_py/persistence/files.py:27`, `src/metasocli_py/persistence/files.py:31`, `src/metasocli_py/persistence/files.py:38`, `src/metasocli_py/persistence/files.py:40` |
| `PLAN_IDENTITY` | `src/metasocli_py/video/planning.py:178` |
| `PLAN_STALE` | `src/metasocli_py/video/execution.py:170`, `src/metasocli_py/video/planning.py:168`, `src/metasocli_py/video/planning.py:188`, `src/metasocli_py/video/planning.py:192` |
| `POLL_LIMIT` | `src/metasocli_py/video/context_ir.py:208`, `src/metasocli_py/video/execution.py:228` |
| `PROMPT_CHANGED` | `src/metasocli_py/application/story.py:126` |
| `PROMPT_LIMIT` | `src/metasocli_py/domain/text.py:113` |
| `PROMPT_REPLACEMENT_KIND` | `src/metasocli_py/application/story.py:207` |
| `PROMPT_REPLACEMENT_STALE` | `src/metasocli_py/application/story.py:242` |
| `PROVIDER_AUTHORIZATION` | `src/metasocli_py/video/execution.py:489` |
| `PROVIDER_CONTRACT` | `src/metasocli_py/providers/metaso.py:51`, `src/metasocli_py/providers/metaso.py:53` |
| `PROVIDER_HTTP` | `src/metasocli_py/providers/metaso.py:58` |
| `PROVIDER_UNREACHABLE` | `src/metasocli_py/providers/http.py:123` |
| `QUERY_CONTRACT` | `src/metasocli_py/providers/metaso.py:71`, `src/metasocli_py/providers/metaso.py:74`, `src/metasocli_py/providers/metaso.py:77`, `src/metasocli_py/providers/metaso.py:82`, `src/metasocli_py/providers/metaso.py:86`, `src/metasocli_py/video/execution.py:256` |
| `RECEIPT_IDENTITY` | `src/metasocli_py/video/execution.py:58`, `src/metasocli_py/video/execution.py:72` |
| `RECIPE_CONFLICT` | `src/metasocli_py/application/assets.py:34`, `src/metasocli_py/application/story.py:153` |
| `RECIPE_DEPENDENCY` | `src/metasocli_py/application/story.py:78`, `src/metasocli_py/application/story.py:85`, `src/metasocli_py/application/story.py:88` |
| `RECORD_INTEGRITY` | `src/metasocli_py/images/workflow.py:290`, `src/metasocli_py/persistence/codec.py:131` |
| `REMOTE_MEDIA_CHANGED` | `src/metasocli_py/video/context_ir.py:121`, `src/metasocli_py/video/execution.py:167` |
| `REPLACE_BUSY` | `src/metasocli_py/persistence/files.py:100` |
| `REQUEST_LIMIT` | `src/metasocli_py/video/planning.py:112` |
| `RESOLUTION_IDENTITY` | `src/metasocli_py/images/recovery.py:58`, `src/metasocli_py/images/recovery.py:68` |
| `RESOLUTION_NOT_ALLOWED` | `src/metasocli_py/images/recovery.py:53` |
| `RESOLUTION_REQUIRED` | `src/metasocli_py/images/recovery.py:55` |
| `RESOLUTION_SOURCE` | `src/metasocli_py/images/recovery.py:61` |
| `RESOLUTION_UNPROVEN` | `src/metasocli_py/images/recovery.py:74` |
| `RESPONSE_ENCODING` | `src/metasocli_py/providers/http.py:120` |
| `RESPONSE_LIMIT` | `src/metasocli_py/providers/http.py:101`, `src/metasocli_py/providers/http.py:108` |
| `RESPONSE_TRUNCATED` | `src/metasocli_py/providers/http.py:114` |
| `RESULT_LINK_REQUIRED` | `src/metasocli_py/images/recovery.py:38` |
| `RESULT_METADATA` | `src/metasocli_py/video/execution.py:118` |
| `RETRY_ALREADY_AUTHORIZED` | `src/metasocli_py/images/workflow.py:673`, `src/metasocli_py/video/retry.py:28` |
| `RETRY_ANCESTRY` | `src/metasocli_py/images/workflow.py:649` |
| `RETRY_EVIDENCE_CONFLICT` | `src/metasocli_py/video/retry.py:52` |
| `RETRY_IDENTITY` | `src/metasocli_py/video/retry.py:20` |
| `RETRY_NOT_ALLOWED` | `src/metasocli_py/images/recovery.py:31`, `src/metasocli_py/video/retry.py:31` |
| `RETRY_NOT_LATEST` | `src/metasocli_py/video/retry.py:37` |
| `RETRY_SUPERSEDED` | `src/metasocli_py/video/execution.py:462` |
| `ROOT_NOT_EMPTY` | `src/metasocli_py/application/story.py:61` |
| `RUNTIME_CONFLICT` | `src/metasocli_py/images/workflow.py:639`, `src/metasocli_py/video/execution.py:377` |
| `SCOPE_AMBIGUOUS` | `src/metasocli_py/video/planning.py:140` |
| `SCOPE_CHANGED` | `src/metasocli_py/cli.py:272` |
| `SEGMENT_MISSING` | `src/metasocli_py/application/story.py:193`, `src/metasocli_py/video/context_ir.py:92`, `src/metasocli_py/video/single.py:24` |
| `SKILL_INSTALL_CONFLICT` | `src/metasocli_py/application/skills.py:53`, `src/metasocli_py/application/skills.py:56`, `src/metasocli_py/application/skills.py:59`, `src/metasocli_py/application/skills.py:73`, `src/metasocli_py/application/skills.py:77`, `src/metasocli_py/application/skills.py:83` |
| `SKILL_NOT_FOUND` | `src/metasocli_py/application/skills.py:97` |
| `SOURCE_CHANGED` | `src/metasocli_py/application/story.py:248`, `src/metasocli_py/application/story.py:251`, `src/metasocli_py/video/planning.py:66`, `src/metasocli_py/video/planning.py:71` |
| `SOURCE_COVERAGE` | `src/metasocli_py/domain/text.py:54`, `src/metasocli_py/domain/text.py:59` |
| `STAGE_UNRESOLVED` | `src/metasocli_py/application/stages.py:38`, `src/metasocli_py/application/stages.py:43` |
| `STOPPED` | `src/metasocli_py/cli.py:401` |
| `TASK_ID_INVALID` | `src/metasocli_py/providers/metaso.py:14` |
| `TASK_LINK_CONFLICT` | `src/metasocli_py/application/stages.py:16`, `src/metasocli_py/video/capacity.py:221`, `src/metasocli_py/video/capacity.py:288`, `src/metasocli_py/video/capacity.py:82` |
| `TASK_LINK_REQUIRED` | `src/metasocli_py/video/single.py:47`, `src/metasocli_py/video/single.py:50` |
| `TEST_ENDPOINT` | `src/metasocli_py/providers/http.py:60`, `src/metasocli_py/providers/http.py:80`, `src/metasocli_py/providers/yiciyuang.py:17` |
| `TRANSACTION_CONFLICT` | `src/metasocli_py/persistence/files.py:200` |
| `TRANSACTION_CORRUPT` | `src/metasocli_py/persistence/files.py:194` |
| `UNKNOWN_ACCEPTANCE_REQUIRED` | `src/metasocli_py/images/workflow.py:669`, `src/metasocli_py/video/retry.py:33` |
| `UNKNOWN_REFERENCE` | `src/metasocli_py/domain/text.py:106`, `src/metasocli_py/domain/text.py:111` |
| `URL_UNSAFE` | `src/metasocli_py/providers/http.py:138`, `src/metasocli_py/providers/http.py:40` |
| `UTF16_BOUNDARY` | `src/metasocli_py/domain/text.py:46` |
| `VIDEO_CHANGED` | `src/metasocli_py/media/inspect.py:205` |
| `VIDEO_DURATION` | `src/metasocli_py/video/execution.py:131` |
| `VIDEO_INVALID` | `src/metasocli_py/media/inspect.py:129`, `src/metasocli_py/media/inspect.py:134`, `src/metasocli_py/media/inspect.py:139`, `src/metasocli_py/media/inspect.py:149`, `src/metasocli_py/media/inspect.py:160`, `src/metasocli_py/media/inspect.py:166`, `src/metasocli_py/media/inspect.py:171`, `src/metasocli_py/media/inspect.py:178`, `src/metasocli_py/media/inspect.py:182`, `src/metasocli_py/media/inspect.py:186`, `src/metasocli_py/media/inspect.py:191`, `src/metasocli_py/media/inspect.py:202`, `src/metasocli_py/media/inspect.py:207`, `src/metasocli_py/video/execution.py:127` |
| `VIDEO_RATIO` | `src/metasocli_py/video/execution.py:136` |
| `YAML_FEATURE` | `src/metasocli_py/persistence/codec.py:107` |
