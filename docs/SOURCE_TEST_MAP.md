# 源测试场景映射

实际基线为 54 个 TypeScript 测试文件，另有 reference_image_skill_test.py，共 55 个测试文件。全部已读。

映射按业务场景及验证方法建立；没有声称每个旧断言都机械移植。旧运行格式、Node锁实现和自动POST退避按本次新协议明确替换，见 FEATURE_MATRIX.md。通过/失败/跳过以最终pytest XML为准。

| 固定基线测试 | Python证据 | 对照场景/明确变化 |
|---|---|---|
| `asset-replacement.test.ts` | [test_local_story.py](../tests/test_local_story.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_foundation.py](../tests/test_foundation.py) | 原ID、6集11段、并发替换、原文/旁白UTF-16、计划失效；scripts/benchmark.py另做11条完整payload差分 |
| `audio.test.ts` | [test_foundation.py](../tests/test_foundation.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py) | PCM/float WAV、VBR/ID3/Xing、错误元数据；ffmpeg合成4秒音视频实际解码 |
| `batch-known-failure-retry.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py) | 一次稳定新尝试、A/B/C、授权范围、损坏成片同伴恢复、原ID不重发；新记录不接受旧trace格式 |
| `canonical.test.ts` | [test_foundation.py](../tests/test_foundation.py) | 新JCS向量及缺失/null/false/0；不沿用旧localeCompare结构化哈希 |
| `capacity-auto-release.test.ts` | [test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_video_http.py](../tests/test_video_http.py)、[test_network_atomic.py](../tests/test_network_atomic.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | R3观察水位/终态/迟到ID/5held/来源证据、公平票据与项目限额；不迁移旧ack格式 |
| `capacity-dispatch.test.ts` | [test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_video_http.py](../tests/test_video_http.py)、[test_network_atomic.py](../tests/test_network_atomic.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | R3观察水位/终态/迟到ID/5held/来源证据、公平票据与项目限额；不迁移旧ack格式 |
| `cli.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py) | 实际CLI、请求契约、inline=true、提交意图/回执；scripts/package_smoke.py另验独立wheel |
| `client.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py) | 实际CLI、请求契约、inline=true、提交意图/回执；scripts/package_smoke.py另验独立wheel |
| `context-ir-contract.test.ts` | [test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py) | 显式独立请求/恢复/审核/派生、等价准备重新绑定、旧派生review不可覆盖 |
| `context-ir-legacy.test.ts` | [test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py) | 旧活跃任务不接管；合成静态内容导入；新IR记录自有严格身份，非旧记录直接兼容 |
| `context-ir-recovery.test.ts` | [test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py) | 显式独立请求/恢复/审核/派生、等价准备重新绑定、旧派生review不可覆盖 |
| `context-ir-reuse.test.ts` | [test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py) | 显式独立请求/恢复/审核/派生、等价准备重新绑定、旧派生review不可覆盖 |
| `context-ir.test.ts` | [test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py) | 显式独立请求/恢复/审核/派生、等价准备重新绑定、旧派生review不可覆盖 |
| `coordinator-boundaries.test.ts` | [test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_video_http.py](../tests/test_video_http.py)、[test_network_atomic.py](../tests/test_network_atomic.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | R3观察水位/终态/迟到ID/5held/来源证据、公平票据与项目限额；不迁移旧ack格式 |
| `credentials.test.ts` | [test_credentials_skills.py](../tests/test_credentials_skills.py) | 独立变量/假token/真DPAPI/短时本机表单；旧凭据不读取 |
| `cross-project-ack.test.ts` | [test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_video_http.py](../tests/test_video_http.py)、[test_network_atomic.py](../tests/test_network_atomic.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | R3观察水位/终态/迟到ID/5held/来源证据、公平票据与项目限额；不迁移旧ack格式 |
| `duration.test.ts` | [test_local_story.py](../tests/test_local_story.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_foundation.py](../tests/test_foundation.py) | 原ID、6集11段、并发替换、原文/旁白UTF-16、计划失效；scripts/benchmark.py另做11条完整payload差分 |
| `image-2k-landscape.test.ts` | [test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_foundation.py](../tests/test_foundation.py)、[test_image_recovery.py](../tests/test_image_recovery.py) | 显式规格、严格profile、去噪原文/类型/幂等；保留模板资源 |
| `image-api-boundaries.test.ts` | [test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_foundation.py](../tests/test_foundation.py)、[test_image_recovery.py](../tests/test_image_recovery.py) | 显式规格、严格profile、去噪原文/类型/幂等；保留模板资源 |
| `image-api-http.test.ts` | [test_image_http.py](../tests/test_image_http.py)、[test_image_recovery.py](../tests/test_image_recovery.py)、[test_network_atomic.py](../tests/test_network_atomic.py) | 真HTTP JSON/multipart/池/总deadline/代理/URL与b64；200独立请求与实际字节归属 |
| `image-api-restart.test.ts` | [test_image_recovery.py](../tests/test_image_recovery.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py) | 完整回执恢复、无自动POST、DAG/人工选择保护、一次后继、丢job证据拒绝；旧ack参数不兼容 |
| `image-api.test.ts` | [test_image_http.py](../tests/test_image_http.py)、[test_image_recovery.py](../tests/test_image_recovery.py)、[test_network_atomic.py](../tests/test_network_atomic.py) | 真HTTP JSON/multipart/池/总deadline/代理/URL与b64；200独立请求与实际字节归属 |
| `image-denoise-prompt.test.ts` | [test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_foundation.py](../tests/test_foundation.py)、[test_image_recovery.py](../tests/test_image_recovery.py) | 显式规格、严格profile、去噪原文/类型/幂等；保留模板资源 |
| `image-existing-unknown-ack.test.ts` | [test_image_recovery.py](../tests/test_image_recovery.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py) | 完整回执恢复、无自动POST、DAG/人工选择保护、一次后继、丢job证据拒绝；旧ack参数不兼容 |
| `image-manual-selection-recovery.test.ts` | [test_image_recovery.py](../tests/test_image_recovery.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py) | 完整回执恢复、无自动POST、DAG/人工选择保护、一次后继、丢job证据拒绝；旧ack参数不兼容 |
| `image-preparation-restart.test.ts` | [test_image_recovery.py](../tests/test_image_recovery.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 严格完整交接/投影校验、持久准备/计划意图、本地collect与index/readiness；同进程校验器 |
| `image-retry-ancestry.test.ts` | [test_image_recovery.py](../tests/test_image_recovery.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py) | 完整回执恢复、无自动POST、DAG/人工选择保护、一次后继、丢job证据拒绝；旧ack参数不兼容 |
| `image-transport.test.ts` | [test_image_http.py](../tests/test_image_http.py)、[test_image_recovery.py](../tests/test_image_recovery.py)、[test_network_atomic.py](../tests/test_network_atomic.py) | 真HTTP JSON/multipart/池/总deadline/代理/URL与b64；200独立请求与实际字节归属 |
| `image-workflow-recovery.test.ts` | [test_image_recovery.py](../tests/test_image_recovery.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 严格完整交接/投影校验、持久准备/计划意图、本地collect与index/readiness；同进程校验器 |
| `image-workflow-review.test.ts` | [test_image_recovery.py](../tests/test_image_recovery.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 严格完整交接/投影校验、持久准备/计划意图、本地collect与index/readiness；同进程校验器 |
| `image-workflow.test.ts` | [test_image_recovery.py](../tests/test_image_recovery.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 严格完整交接/投影校验、持久准备/计划意图、本地collect与index/readiness；同进程校验器 |
| `inline-context-ir.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py) | 实际CLI、请求契约、inline=true、提交意图/回执；scripts/package_smoke.py另验独立wheel |
| `narration.test.ts` | [test_local_story.py](../tests/test_local_story.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_foundation.py](../tests/test_foundation.py) | 原ID、6集11段、并发替换、原文/旁白UTF-16、计划失效；scripts/benchmark.py另做11条完整payload差分 |
| `planning.test.ts` | [test_local_story.py](../tests/test_local_story.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_foundation.py](../tests/test_foundation.py) | 原ID、6集11段、并发替换、原文/旁白UTF-16、计划失效；scripts/benchmark.py另做11条完整payload差分 |
| `project-isolation-compat.test.ts` | [test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py) | 旧活跃任务不接管；合成静态内容导入；新IR记录自有严格身份，非旧记录直接兼容 |
| `project-isolation-images.test.ts` | [test_image_recovery.py](../tests/test_image_recovery.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py) | 跨故事未知隔离、共享已知配额、同故事提交lease、失败不取消其他回包 |
| `project-isolation-video.test.ts` | [test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_video_http.py](../tests/test_video_http.py)、[test_network_atomic.py](../tests/test_network_atomic.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | R3观察水位/终态/迟到ID/5held/来源证据、公平票据与项目限额；不迁移旧ack格式 |
| `prompt-replacement-cli.test.ts` | [test_local_story.py](../tests/test_local_story.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_foundation.py](../tests/test_foundation.py) | 原ID、6集11段、并发替换、原文/旁白UTF-16、计划失效；scripts/benchmark.py另做11条完整payload差分 |
| `prompt-replacement.test.ts` | [test_local_story.py](../tests/test_local_story.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_foundation.py](../tests/test_foundation.py) | 原ID、6集11段、并发替换、原文/旁白UTF-16、计划失效；scripts/benchmark.py另做11条完整payload差分 |
| `recovery.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 8段持续补位、慢下载分离、全/部分复用、单次CLI、七类杀进程checkpoint、原请求恢复 |
| `storage-concurrency.test.ts` | [test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_network_atomic.py](../tests/test_network_atomic.py) | 真实Windows进程、事务崩溃、稳定OS锁、原子替换/身份变化；不复制Node可删除PID锁机制 |
| `storage-path-retry.test.ts` | [test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_network_atomic.py](../tests/test_network_atomic.py) | 真实Windows进程、事务崩溃、稳定OS锁、原子替换/身份变化；不复制Node可删除PID锁机制 |
| `storage.test.ts` | [test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_network_atomic.py](../tests/test_network_atomic.py) | 真实Windows进程、事务崩溃、稳定OS锁、原子替换/身份变化；不复制Node可删除PID锁机制 |
| `story.test.ts` | [test_local_story.py](../tests/test_local_story.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_foundation.py](../tests/test_foundation.py) | 原ID、6集11段、并发替换、原文/旁白UTF-16、计划失效；scripts/benchmark.py另做11条完整payload差分 |
| `submit.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py) | 实际CLI、请求契约、inline=true、提交意图/回执；scripts/package_smoke.py另验独立wheel |
| `video-batch-faults.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 8段持续补位、慢下载分离、全/部分复用、单次CLI、七类杀进程checkpoint、原请求恢复 |
| `video-batch.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 8段持续补位、慢下载分离、全/部分复用、单次CLI、七类杀进程checkpoint、原请求恢复 |
| `video-execute-regressions.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py) | 一次稳定新尝试、A/B/C、授权范围、损坏成片同伴恢复、原ID不重发；新记录不接受旧trace格式 |
| `video-execute.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 8段持续补位、慢下载分离、全/部分复用、单次CLI、七类杀进程checkpoint、原请求恢复 |
| `video-recovered-failure-retry.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py) | 一次稳定新尝试、A/B/C、授权范围、损坏成片同伴恢复、原ID不重发；新记录不接受旧trace格式 |
| `video-recovery-boundaries.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py) | 一次稳定新尝试、A/B/C、授权范围、损坏成片同伴恢复、原ID不重发；新记录不接受旧trace格式 |
| `video-run-cli.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 8段持续补位、慢下载分离、全/部分复用、单次CLI、七类杀进程checkpoint、原请求恢复 |
| `video-run.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_capacity_ir.py](../tests/test_capacity_ir.py)、[test_acceptance_edges.py](../tests/test_acceptance_edges.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py) | 8段持续补位、慢下载分离、全/部分复用、单次CLI、七类杀进程checkpoint、原请求恢复 |
| `video-unknown-retry.test.ts` | [test_video_http.py](../tests/test_video_http.py)、[test_retry_ir_edges.py](../tests/test_retry_ir_edges.py)、[test_revision_boundaries.py](../tests/test_revision_boundaries.py)、[test_process_boundaries.py](../tests/test_process_boundaries.py) | 一次稳定新尝试、A/B/C、授权范围、损坏成片同伴恢复、原ID不重发；新记录不接受旧trace格式 |
| `reference_image_skill_test.py` | [test_foundation.py](../tests/test_foundation.py)、[test_credentials_skills.py](../tests/test_credentials_skills.py)、[test_image_recovery.py](../tests/test_image_recovery.py)、[package_smoke.py](../scripts/package_smoke.py) | 单向适配helper、去噪哈希、完整交接、真实回执、六Skill资源/三入口临时安装/独立wheel；不运行旧Node生产代码 |

## Python实际测试函数清单

参数化项及 Hypothesis 样本数不等于独立业务场景数。

### test_acceptance_edges.py

- `test_cli_six_eleven_and_concurrent_replace`
- `test_utf16_narration_relocation_and_ambiguity`
- `test_image_dag_unlock_before_unrelated_finishes`
- `test_image_failure_keeps_sibling_receipts_and_quota`
- `test_image_cancel_drains_receipts_without_resubmitting`
- `test_video_partial_and_full_reuse_identity`
- `test_static_legacy_content_only_and_unknown_rejection`

### test_capacity_ir.py

- `test_query_failure_releases_poll_limit_holds`
- `test_two_stories_priority_and_spare_capacity`
- `test_explicit_ir_review_derive_video_false`

### test_credentials_skills.py

- `test_dpapi_backup_failed_replace_and_status`
- `test_local_form_host_origin_token_single_use`
- `test_three_skills_temp_discovery_and_rollback`

### test_foundation.py

- `test_utf16_source_and_no_trimming`
- `test_utf16_round_trip`
- `test_jcs_vectors_and_distinctions`
- `test_reject_ambiguous_input`
- `test_strict_types`
- `test_denoise_idempotent_and_type_specific`
- `test_audio_pcm_float_vbr_id3_and_false_metadata`

### test_image_http.py

- `test_200_images_real_http`
- `test_real_total_deadline`

### test_image_recovery.py

- `test_image_status_no_automatic_post_retry`
- `test_image_download_or_truncation_never_regenerates`
- `test_actual_multipart_order_bytes_names_mime`
- `test_preparation_full_handoff_and_collect`
- `test_other_story_unknown_does_not_block_images`

### test_independent_review.py

- `test_new_scope_refreshes_same_story_old_task_ids`
- `test_explicit_retry_after_correcting_auth_can_submit_once`
- `test_image_quota_intent_window_has_durable_recovery`

### test_local_story.py

- `test_six_episodes_eleven_segments_replace`
- `test_invalid_duration_bool_and_string`

### test_network_atomic.py

- `test_direct_proxy_environment_real_http`
- `test_windows_actual_sharing_denial_bounded_atomic_retry`
- `test_file_identity_changes_between_stat_and_open_rejected`
- `test_five_restored_held_tasks_stop_new_reservations`

### test_process_boundaries.py

- `test_real_child_stable_lock_owner_and_crash`
- `test_real_transaction_crash_rolls_forward`
- `test_killed_image_recovers_without_post`
- `test_killed_video_never_reposts`
- `test_windows_path_boundaries`

### test_repair_images.py

- `test_real_child_image_protocol_interruptions`
- `test_two_real_recovery_processes_share_one_prepared_admission`
- `test_live_owner_then_dead_unsent_reservation_frees_other_story`
- `test_prepared_recover_is_zero_post_and_admission_is_idempotent_rpm`
- `test_unproven_orphans_are_not_released`
- `test_protocol_timestamps_and_changed_prepared_inputs_fail_closed`
- `test_released_prepared_readmission_charges_new_rpm_window`
- `test_image_protocol_local_write_counts`
- `test_admission_rechecked_before_post`

### test_repair_video.py

- `test_normal_schedule_has_no_additional_history_gets`
- `test_history_parallel_refill_only_selected_delivery`
- `test_history_r3_boundaries`
- `test_selected_dedup_and_late_active_cannot_overwrite_terminal`
- `test_auth_fixed_original_scope_and_exactly_once_retry`
- `test_new_retry_rejection_stops_this_invocation`

### test_retry_ir_edges.py

- `test_unknown_late_id_obsolete_grant_and_known_failure_retry`
- `test_ir_rebind_equivalent_segment_and_preserve_old_derived_plan`
- `test_ir_complete_response_and_result_recover_without_post`
- `test_real_ffmpeg_av_validation`

### test_revision_boundaries.py

- `test_url_two_download_lanes_and_local_reports`
- `test_lost_image_job_with_receipt_never_posts_again`
- `test_image_request_resealed_tamper_rejected`
- `test_known_shared_image_limit_survives_unconfigured_second_profile`
- `test_manual_video_task_link_preserves_observed_terminal`
- `test_observation_watermark_blocks_stale_running_and_terminal_absorbs`
- `test_corrupt_output_does_not_strand_peer_and_missing_output_is_incomplete`
- `test_register_missing_slot_and_old_source_error_cannot_undo_fresh_evidence`
- `test_explicit_image_specification_blocks_only_conflicting_items`
- `test_released_same_story_unknown_does_not_block_different_segment`
- `test_restricted_retry_expands_only_with_explicit_full_batch_authorization`

### test_video_http.py

- `test_eight_segments_refill_before_slow_download`
- `test_unknown_no_resubmit_and_exact_one_retry`
- `test_r3_terminal_late_active_and_watermarks`

