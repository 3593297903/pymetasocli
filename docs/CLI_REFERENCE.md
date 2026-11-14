# 当前 CLI 帮助

从本版本实际 argparse 解析器生成；以新参数为准，不兼容的旧参数见 FEATURE_MATRIX.md。

## metasocli-py

```text
usage: metasocli-py [-h] [--version]
                    {init,import,assets,prompts,plan,video,batch,generate,resume,download,status,doctor,attach-task,auth,images,legacy,skills,context-ir} ...

Independent Python story and generation CLI

positional arguments:
  {init,import,assets,prompts,plan,video,batch,generate,resume,download,status,doctor,attach-task,auth,images,legacy,skills,context-ir}

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
```

## metasocli-py init

```text
usage: metasocli-py init [-h] --root ROOT [--json] --name NAME

options:
  -h, --help   show this help message and exit
  --root ROOT
  --json
  --name NAME
```

## metasocli-py import

```text
usage: metasocli-py import [-h] --root ROOT [--json] (--draft DRAFT |
                           --file FILE) [--episode EPISODE]
                           [--kind {script,video-prompts}]
                           [--duration DURATION] [--replace]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --draft DRAFT
  --file FILE
  --episode EPISODE
  --kind {script,video-prompts}
  --duration DURATION
  --replace
```

## metasocli-py assets

```text
usage: metasocli-py assets [-h] {register,list} ...

positional arguments:
  {register,list}

options:
  -h, --help       show this help message and exit
```

## metasocli-py assets register

```text
usage: metasocli-py assets register [-h] --root ROOT [--json] --id ID
                                    (--file FILE | --url URL)
                                    [--provenance {user,imagegen}]
                                    [--expected-sha256 EXPECTED_SHA256]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --id ID
  --file FILE
  --url URL
  --provenance {user,imagegen}
  --expected-sha256 EXPECTED_SHA256
```

## metasocli-py assets list

```text
usage: metasocli-py assets list [-h] --root ROOT [--json]

options:
  -h, --help   show this help message and exit
  --root ROOT
  --json
```

## metasocli-py prompts

```text
usage: metasocli-py prompts [-h] {replace} ...

positional arguments:
  {replace}

options:
  -h, --help  show this help message and exit
```

## metasocli-py prompts replace

```text
usage: metasocli-py prompts replace [-h] --root ROOT [--json]
                                    --episode EPISODE --segment SEGMENT
                                    --file FILE
                                    [--expected-sha256 EXPECTED_SHA256]
                                    [--expected-prompt-hash EXPECTED_PROMPT_HASH]
                                    [--narration-cues NARRATION_CUES]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --episode EPISODE
  --segment SEGMENT
  --file FILE
  --expected-sha256 EXPECTED_SHA256
  --expected-prompt-hash EXPECTED_PROMPT_HASH
  --narration-cues NARRATION_CUES
```

## metasocli-py plan

```text
usage: metasocli-py plan [-h] --root ROOT [--json] --episode EPISODE
                         [--workflow {h3-inline-ir,h3-context-ir}]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --episode EPISODE
  --workflow {h3-inline-ir,h3-context-ir}
```

## metasocli-py video

```text
usage: metasocli-py video [-h] {run,execute} ...

positional arguments:
  {run,execute}

options:
  -h, --help     show this help message and exit
```

## metasocli-py video run

```text
usage: metasocli-py video run [-h] --root ROOT [--json] [--episodes EPISODES |
                              --selection SELECTION | --batch BATCH]
                              [--concurrency CONCURRENCY]
                              [--expect-scope EXPECT_SCOPE] [--verify-av]
                              [--confirm] [--max-polls MAX_POLLS]
                              [--poll-ms POLL_MS]
                              [--capacity-wait-ms CAPACITY_WAIT_MS]
                              [--capacity-poll-ms CAPACITY_POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --episodes EPISODES
  --selection SELECTION
  --batch BATCH
  --concurrency CONCURRENCY
  --expect-scope EXPECT_SCOPE
  --verify-av
  --confirm
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
```

## metasocli-py video execute

```text
usage: metasocli-py video execute [-h] --root ROOT [--json]
                                  [--episodes EPISODES |
                                  --selection SELECTION | --batch BATCH]
                                  [--concurrency CONCURRENCY]
                                  [--expect-scope EXPECT_SCOPE] [--verify-av]
                                  [--confirm] [--max-polls MAX_POLLS]
                                  [--poll-ms POLL_MS]
                                  [--capacity-wait-ms CAPACITY_WAIT_MS]
                                  [--capacity-poll-ms CAPACITY_POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --episodes EPISODES
  --selection SELECTION
  --batch BATCH
  --concurrency CONCURRENCY
  --expect-scope EXPECT_SCOPE
  --verify-av
  --confirm
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
```

## metasocli-py batch

```text
usage: metasocli-py batch [-h] {plan,run,resume,status,retry,register} ...

positional arguments:
  {plan,run,resume,status,retry,register}

options:
  -h, --help            show this help message and exit
```

## metasocli-py batch plan

```text
usage: metasocli-py batch plan [-h] --root ROOT [--json]
                               (--episodes EPISODES | --selection SELECTION |
                               --all-episodes) [--concurrency CONCURRENCY]
                               [--confirm] [--max-polls MAX_POLLS]
                               [--poll-ms POLL_MS]
                               [--capacity-wait-ms CAPACITY_WAIT_MS]
                               [--capacity-poll-ms CAPACITY_POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --episodes EPISODES
  --selection SELECTION
  --all-episodes
  --concurrency CONCURRENCY
  --confirm
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
```

## metasocli-py batch run

```text
usage: metasocli-py batch run [-h] --root ROOT [--json] --batch BATCH
                              [--confirm] [--max-polls MAX_POLLS]
                              [--poll-ms POLL_MS]
                              [--capacity-wait-ms CAPACITY_WAIT_MS]
                              [--capacity-poll-ms CAPACITY_POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --batch BATCH
  --confirm
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
```

## metasocli-py batch resume

```text
usage: metasocli-py batch resume [-h] --root ROOT [--json] --batch BATCH
                                 [--confirm] [--max-polls MAX_POLLS]
                                 [--poll-ms POLL_MS]
                                 [--capacity-wait-ms CAPACITY_WAIT_MS]
                                 [--capacity-poll-ms CAPACITY_POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --batch BATCH
  --confirm
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
```

## metasocli-py batch status

```text
usage: metasocli-py batch status [-h] --root ROOT [--json] --batch BATCH
                                 [--confirm] [--max-polls MAX_POLLS]
                                 [--poll-ms POLL_MS]
                                 [--capacity-wait-ms CAPACITY_WAIT_MS]
                                 [--capacity-poll-ms CAPACITY_POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --batch BATCH
  --confirm
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
```

## metasocli-py batch retry

```text
usage: metasocli-py batch retry [-h] --root ROOT [--json] --batch BATCH
                                [--confirm] [--max-polls MAX_POLLS]
                                [--poll-ms POLL_MS]
                                [--capacity-wait-ms CAPACITY_WAIT_MS]
                                [--capacity-poll-ms CAPACITY_POLL_MS]
                                --operation OPERATION
                                [--accept-unknown-result]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --batch BATCH
  --confirm
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
  --operation OPERATION
  --accept-unknown-result
```

## metasocli-py batch register

```text
usage: metasocli-py batch register [-h] --root ROOT [--json] [--batch BATCH]
                                   [--confirm] [--max-polls MAX_POLLS]
                                   [--poll-ms POLL_MS]
                                   [--capacity-wait-ms CAPACITY_WAIT_MS]
                                   [--capacity-poll-ms CAPACITY_POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --batch BATCH
  --confirm
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
```

## metasocli-py generate

```text
usage: metasocli-py generate [-h] --root ROOT [--json] [--operation OPERATION]
                             --plan PLAN [--segment SEGMENT] [--confirm]
                             [--submit-only] [--retry-of RETRY_OF]
                             [--accept-unknown-result] [--max-polls MAX_POLLS]
                             [--poll-ms POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --operation OPERATION
  --plan PLAN
  --segment SEGMENT
  --confirm
  --submit-only
  --retry-of RETRY_OF
  --accept-unknown-result
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
```

## metasocli-py resume

```text
usage: metasocli-py resume [-h] --root ROOT [--json] --operation OPERATION
                           [--max-polls MAX_POLLS] [--poll-ms POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --operation OPERATION
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
```

## metasocli-py download

```text
usage: metasocli-py download [-h] --root ROOT [--json] --operation OPERATION
                             [--max-polls MAX_POLLS] [--poll-ms POLL_MS]
                             [--redownload-missing]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --operation OPERATION
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
  --redownload-missing
```

## metasocli-py status

```text
usage: metasocli-py status [-h] --root ROOT [--json] [--operation OPERATION]
                           [--remote]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --operation OPERATION
  --remote
```

## metasocli-py doctor

```text
usage: metasocli-py doctor [-h] --root ROOT [--json]

options:
  -h, --help   show this help message and exit
  --root ROOT
  --json
```

## metasocli-py attach-task

```text
usage: metasocli-py attach-task [-h] --root ROOT [--json]
                                --operation OPERATION --task TASK
                                [--confirm-task-link]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --operation OPERATION
  --task TASK
  --confirm-task-link
```

## metasocli-py auth

```text
usage: metasocli-py auth [-h] {connect,status} ...

positional arguments:
  {connect,status}

options:
  -h, --help        show this help message and exit
```

## metasocli-py auth connect

```text
usage: metasocli-py auth connect [-h]

options:
  -h, --help  show this help message and exit
```

## metasocli-py auth status

```text
usage: metasocli-py auth status [-h] [--decrypt]

options:
  -h, --help  show this help message and exit
  --decrypt
```

## metasocli-py images

```text
usage: metasocli-py images [-h]
                           {prepare,plan,run,resume,collect,status,recover,retry,attach-result,resolve,auth-connect,auth-status} ...

positional arguments:
  {prepare,plan,run,resume,collect,status,recover,retry,attach-result,resolve,auth-connect,auth-status}

options:
  -h, --help            show this help message and exit
```

## metasocli-py images prepare

```text
usage: metasocli-py images prepare [-h] --root ROOT [--json] [--summary]
                                   (--batch BATCH | --preparation PREPARATION)

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --batch BATCH
  --preparation PREPARATION
```

## metasocli-py images plan

```text
usage: metasocli-py images plan [-h] --root ROOT [--json] [--summary]
                                (--assets ASSETS | --episodes EPISODES |
                                --selection SELECTION | --all-episodes)
                                [--profile PROFILE] [--restart-of RESTART_OF]
                                [--submission-mode {all-ready}]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --assets ASSETS
  --episodes EPISODES
  --selection SELECTION
  --all-episodes
  --profile PROFILE
  --restart-of RESTART_OF
  --submission-mode {all-ready}
```

## metasocli-py images run

```text
usage: metasocli-py images run [-h] --root ROOT [--json] [--summary]
                               [--capacity-wait-ms CAPACITY_WAIT_MS]
                               [--capacity-poll-ms CAPACITY_POLL_MS]
                               [--plan PLAN] [--preparation PREPARATION]
                               [--confirm] [--accept-unknown-result]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
  --plan PLAN
  --preparation PREPARATION
  --confirm
  --accept-unknown-result
```

## metasocli-py images resume

```text
usage: metasocli-py images resume [-h] --root ROOT [--json] [--summary]
                                  [--capacity-wait-ms CAPACITY_WAIT_MS]
                                  [--capacity-poll-ms CAPACITY_POLL_MS]
                                  [--plan PLAN] [--preparation PREPARATION]
                                  [--confirm] [--accept-unknown-result]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
  --plan PLAN
  --preparation PREPARATION
  --confirm
  --accept-unknown-result
```

## metasocli-py images collect

```text
usage: metasocli-py images collect [-h] --root ROOT [--json] [--summary]
                                   [--plan PLAN] [--preparation PREPARATION]
                                   [--confirm] [--accept-unknown-result]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --plan PLAN
  --preparation PREPARATION
  --confirm
  --accept-unknown-result
```

## metasocli-py images status

```text
usage: metasocli-py images status [-h] --root ROOT [--json] [--summary]
                                  [--plan PLAN] [--preparation PREPARATION]
                                  [--confirm] [--accept-unknown-result]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --plan PLAN
  --preparation PREPARATION
  --confirm
  --accept-unknown-result
```

## metasocli-py images recover

```text
usage: metasocli-py images recover [-h] --root ROOT [--json] [--summary]
                                   --operation OPERATION [--confirm]
                                   [--accept-unknown-result]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --operation OPERATION
  --confirm
  --accept-unknown-result
```

## metasocli-py images retry

```text
usage: metasocli-py images retry [-h] --root ROOT [--json] [--summary]
                                 [--capacity-wait-ms CAPACITY_WAIT_MS]
                                 [--capacity-poll-ms CAPACITY_POLL_MS]
                                 --operation OPERATION [--confirm]
                                 [--accept-unknown-result]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --capacity-wait-ms CAPACITY_WAIT_MS
  --capacity-poll-ms CAPACITY_POLL_MS
  --operation OPERATION
  --confirm
  --accept-unknown-result
```

## metasocli-py images attach-result

```text
usage: metasocli-py images attach-result [-h] --root ROOT [--json] [--summary]
                                         --operation OPERATION [--confirm]
                                         [--accept-unknown-result] --file FILE
                                         --expected-sha256 EXPECTED_SHA256
                                         [--confirm-result-link]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --operation OPERATION
  --confirm
  --accept-unknown-result
  --file FILE
  --expected-sha256 EXPECTED_SHA256
  --confirm-result-link
```

## metasocli-py images resolve

```text
usage: metasocli-py images resolve [-h] --root ROOT [--json] [--summary]
                                   --operation OPERATION [--confirm]
                                   [--accept-unknown-result]
                                   --evidence EVIDENCE
                                   --outcome {not-created,failed}
                                   [--confirm-resolution]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --summary
  --operation OPERATION
  --confirm
  --accept-unknown-result
  --evidence EVIDENCE
  --outcome {not-created,failed}
  --confirm-resolution
```

## metasocli-py images auth-connect

```text
usage: metasocli-py images auth-connect [-h]

options:
  -h, --help  show this help message and exit
```

## metasocli-py images auth-status

```text
usage: metasocli-py images auth-status [-h]

options:
  -h, --help  show this help message and exit
```

## metasocli-py legacy

```text
usage: metasocli-py legacy [-h] {inspect,import-content} ...

positional arguments:
  {inspect,import-content}

options:
  -h, --help            show this help message and exit
```

## metasocli-py legacy inspect

```text
usage: metasocli-py legacy inspect [-h] --source SOURCE

options:
  -h, --help       show this help message and exit
  --source SOURCE
```

## metasocli-py legacy import-content

```text
usage: metasocli-py legacy import-content [-h] --source SOURCE --root ROOT
                                          [--json] --name NAME

options:
  -h, --help       show this help message and exit
  --source SOURCE
  --root ROOT
  --json
  --name NAME
```

## metasocli-py skills

```text
usage: metasocli-py skills [-h] {list,read,install,uninstall} ...

positional arguments:
  {list,read,install,uninstall}

options:
  -h, --help            show this help message and exit
```

## metasocli-py skills list

```text
usage: metasocli-py skills list [-h]

options:
  -h, --help  show this help message and exit
```

## metasocli-py skills read

```text
usage: metasocli-py skills read [-h] name

positional arguments:
  name

options:
  -h, --help  show this help message and exit
```

## metasocli-py skills install

```text
usage: metasocli-py skills install [-h] --user-dir USER_DIR

options:
  -h, --help           show this help message and exit
  --user-dir USER_DIR
```

## metasocli-py skills uninstall

```text
usage: metasocli-py skills uninstall [-h] --user-dir USER_DIR

options:
  -h, --help           show this help message and exit
  --user-dir USER_DIR
```

## metasocli-py context-ir

```text
usage: metasocli-py context-ir [-h]
                               {run,resume,review,derive,status,attach-task} ...

positional arguments:
  {run,resume,review,derive,status,attach-task}

options:
  -h, --help            show this help message and exit
```

## metasocli-py context-ir run

```text
usage: metasocli-py context-ir run [-h] --root ROOT [--json] [--plan PLAN]
                                   [--segment SEGMENT] [--operation OPERATION]
                                   [--file FILE] [--confirm]
                                   [--retry-of RETRY_OF] [--task TASK]
                                   [--submit-only] [--max-polls MAX_POLLS]
                                   [--poll-ms POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --plan PLAN
  --segment SEGMENT
  --operation OPERATION
  --file FILE
  --confirm
  --retry-of RETRY_OF
  --task TASK
  --submit-only
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
```

## metasocli-py context-ir resume

```text
usage: metasocli-py context-ir resume [-h] --root ROOT [--json] [--plan PLAN]
                                      [--segment SEGMENT]
                                      [--operation OPERATION] [--file FILE]
                                      [--confirm] [--retry-of RETRY_OF]
                                      [--task TASK] [--submit-only]
                                      [--max-polls MAX_POLLS]
                                      [--poll-ms POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --plan PLAN
  --segment SEGMENT
  --operation OPERATION
  --file FILE
  --confirm
  --retry-of RETRY_OF
  --task TASK
  --submit-only
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
```

## metasocli-py context-ir review

```text
usage: metasocli-py context-ir review [-h] --root ROOT [--json] [--plan PLAN]
                                      [--segment SEGMENT]
                                      [--operation OPERATION] [--file FILE]
                                      [--confirm] [--retry-of RETRY_OF]
                                      [--task TASK] [--submit-only]
                                      [--max-polls MAX_POLLS]
                                      [--poll-ms POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --plan PLAN
  --segment SEGMENT
  --operation OPERATION
  --file FILE
  --confirm
  --retry-of RETRY_OF
  --task TASK
  --submit-only
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
```

## metasocli-py context-ir derive

```text
usage: metasocli-py context-ir derive [-h] --root ROOT [--json] [--plan PLAN]
                                      [--segment SEGMENT]
                                      [--operation OPERATION] [--file FILE]
                                      [--confirm] [--retry-of RETRY_OF]
                                      [--task TASK] [--submit-only]
                                      [--max-polls MAX_POLLS]
                                      [--poll-ms POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --plan PLAN
  --segment SEGMENT
  --operation OPERATION
  --file FILE
  --confirm
  --retry-of RETRY_OF
  --task TASK
  --submit-only
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
```

## metasocli-py context-ir status

```text
usage: metasocli-py context-ir status [-h] --root ROOT [--json] [--plan PLAN]
                                      [--segment SEGMENT]
                                      [--operation OPERATION] [--file FILE]
                                      [--confirm] [--retry-of RETRY_OF]
                                      [--task TASK] [--submit-only]
                                      [--max-polls MAX_POLLS]
                                      [--poll-ms POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --plan PLAN
  --segment SEGMENT
  --operation OPERATION
  --file FILE
  --confirm
  --retry-of RETRY_OF
  --task TASK
  --submit-only
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
```

## metasocli-py context-ir attach-task

```text
usage: metasocli-py context-ir attach-task [-h] --root ROOT [--json]
                                           [--plan PLAN] [--segment SEGMENT]
                                           [--operation OPERATION]
                                           [--file FILE] [--confirm]
                                           [--retry-of RETRY_OF] [--task TASK]
                                           [--submit-only]
                                           [--max-polls MAX_POLLS]
                                           [--poll-ms POLL_MS]

options:
  -h, --help            show this help message and exit
  --root ROOT
  --json
  --plan PLAN
  --segment SEGMENT
  --operation OPERATION
  --file FILE
  --confirm
  --retry-of RETRY_OF
  --task TASK
  --submit-only
  --max-polls MAX_POLLS
  --poll-ms POLL_MS
```

