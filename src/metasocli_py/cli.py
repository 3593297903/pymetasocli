"""The installed CLI uses fixed API origins; test injection is programmatic only."""
import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, cast

from . import __version__
from .domain.errors import AppError

if TYPE_CHECKING:
    from .video.execution import ExecutionOptions


@dataclass
class Services:
    video_factory: Callable | None = None
    image_factory: Callable | None = None
    image_checkpoint: Callable = lambda _point, _job: None
    execution_options: 'ExecutionOptions | None' = None


class SafeParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **{**kwargs, 'allow_abbrev': False})

    def error(self, message):
        # argparse's default diagnostics echo arbitrary values and credentials.
        raise AppError('CLI_ARGUMENT', 'Invalid command arguments. Use --help for accepted options.')


def parser() -> argparse.ArgumentParser:
    app = SafeParser(prog='metasocli-py', description='Independent Python story and generation CLI')
    app.add_argument('--version', action='version', version='metasocli-py ' + __version__)
    commands = app.add_subparsers(dest='command', required=True)
    def root_options(cmd):
        cmd.add_argument('--root', type=Path, required=True)
        cmd.add_argument('--json', action='store_true')
    init = commands.add_parser('init')
    root_options(init)
    init.add_argument('--name', required=True)
    imp = commands.add_parser('import')
    root_options(imp)
    source = imp.add_mutually_exclusive_group(required=True)
    source.add_argument('--draft', type=Path)
    source.add_argument('--file', type=Path)
    imp.add_argument('--episode')
    imp.add_argument('--kind', choices=['script', 'video-prompts'], default='video-prompts')
    imp.add_argument('--duration', type=float, default=12)
    imp.add_argument('--replace', action='store_true')
    assets = commands.add_parser('assets').add_subparsers(dest='action', required=True)
    register = assets.add_parser('register')
    root_options(register)
    register.add_argument('--id', required=True)
    media = register.add_mutually_exclusive_group(required=True)
    media.add_argument('--file', type=Path)
    media.add_argument('--url')
    register.add_argument('--provenance', choices=['user', 'imagegen'], default='user')
    register.add_argument('--expected-sha256')
    root_options(assets.add_parser('list'))
    prompts = commands.add_parser('prompts').add_subparsers(dest='action', required=True)
    replace = prompts.add_parser('replace')
    root_options(replace)
    for option in ('episode', 'segment'):
        replace.add_argument('--' + option, required=True)
    replace.add_argument('--file', required=True, type=Path)
    replace.add_argument('--expected-sha256')
    replace.add_argument('--expected-prompt-hash')
    replace.add_argument('--narration-cues', type=Path)
    def scope(cmd, *, batch=True):
        group = cmd.add_mutually_exclusive_group(required=not batch)
        group.add_argument('--episodes')
        group.add_argument('--selection', type=Path)
        if batch:
            group.add_argument('--batch')
        else:
            group.add_argument('--all-episodes', action='store_true')
        cmd.add_argument('--concurrency', type=int, default=4)
    plan = commands.add_parser('plan')
    root_options(plan)
    plan.add_argument('--episode', required=True)
    plan.add_argument('--workflow', choices=['h3-inline-ir', 'h3-context-ir'], default='h3-inline-ir')
    for group_name, actions in [('video', ['run', 'execute']), ('batch', ['plan', 'run', 'resume', 'status', 'retry', 'register'])]:
        sub = commands.add_parser(group_name).add_subparsers(dest='action', required=True)
        for action in actions:
            cmd = sub.add_parser(action)
            root_options(cmd)
            if action == 'plan':
                scope(cmd, batch=False)
            elif group_name == 'video':
                scope(cmd)
                cmd.add_argument('--expect-scope')
                cmd.add_argument('--verify-av', action='store_true')
            else:
                cmd.add_argument('--batch', required=action != 'register')
            cmd.add_argument('--confirm', action='store_true')
            cmd.add_argument('--max-polls', type=int, default=60)
            cmd.add_argument('--poll-ms', type=int, default=5000)
            cmd.add_argument('--capacity-wait-ms', type=int, default=30000)
            cmd.add_argument('--capacity-poll-ms', type=int, default=250)
            if action == 'retry':
                cmd.add_argument('--operation', required=True)
                cmd.add_argument('--accept-unknown-result', action='store_true')
    for name in ('generate', 'resume', 'download', 'status', 'doctor', 'attach-task'):
        cmd = commands.add_parser(name)
        root_options(cmd)
        if name not in ('doctor',):
            cmd.add_argument('--operation', required=name in ('resume', 'download', 'attach-task'))
        if name == 'generate':
            cmd.add_argument('--plan', required=True)
            cmd.add_argument('--segment')
            cmd.add_argument('--confirm', action='store_true')
            cmd.add_argument('--submit-only', action='store_true')
            cmd.add_argument('--retry-of')
            cmd.add_argument('--accept-unknown-result', action='store_true')
        if name == 'status':
            cmd.add_argument('--remote', action='store_true')
        if name in ('generate', 'resume', 'download'):
            cmd.add_argument('--max-polls', type=int, default=60)
            cmd.add_argument('--poll-ms', type=int, default=5000)
        if name == 'download':
            cmd.add_argument('--redownload-missing', action='store_true')
        if name == 'attach-task':
            cmd.add_argument('--task', required=True)
            cmd.add_argument('--confirm-task-link', action='store_true')
    auth = commands.add_parser('auth').add_subparsers(dest='action', required=True)
    auth.add_parser('connect')
    auth_status = auth.add_parser('status')
    auth_status.add_argument('--decrypt', action='store_true')
    images = commands.add_parser('images').add_subparsers(dest='action', required=True)
    for action in ('prepare', 'plan', 'run', 'resume', 'collect', 'status', 'recover', 'retry', 'attach-result', 'resolve', 'auth-connect', 'auth-status'):
        cmd = images.add_parser(action)
        if action.startswith('auth-'):
            continue
        root_options(cmd)
        cmd.add_argument('--summary', action='store_true')
        if action in ('run', 'resume', 'retry'):
            cmd.add_argument('--capacity-wait-ms', type=int, default=30000)
            cmd.add_argument('--capacity-poll-ms', type=int, default=250)
        if action == 'prepare':
            source = cmd.add_mutually_exclusive_group(required=True)
            source.add_argument('--batch', type=Path)
            source.add_argument('--preparation')
        elif action == 'plan':
            source = cmd.add_mutually_exclusive_group(required=True)
            source.add_argument('--assets')
            source.add_argument('--episodes')
            source.add_argument('--selection', type=Path)
            source.add_argument('--all-episodes', action='store_true')
            cmd.add_argument('--profile', type=Path)
            cmd.add_argument('--restart-of')
            cmd.add_argument('--submission-mode', choices=['all-ready'], default='all-ready')
        elif action in ('recover', 'retry', 'attach-result', 'resolve'):
            cmd.add_argument('--operation', required=True)
            cmd.add_argument('--confirm', action='store_true')
            cmd.add_argument('--accept-unknown-result', action='store_true')
            if action == 'attach-result':
                cmd.add_argument('--file', required=True, type=Path)
                cmd.add_argument('--expected-sha256', required=True)
                cmd.add_argument('--confirm-result-link', action='store_true')
            if action == 'resolve':
                cmd.add_argument('--evidence', required=True, type=Path)
                cmd.add_argument('--outcome', required=True, choices=['not-created', 'failed'])
                cmd.add_argument('--confirm-resolution', action='store_true')
        else:
            cmd.add_argument('--plan')
            cmd.add_argument('--preparation')
            cmd.add_argument('--confirm', action='store_true')
            cmd.add_argument('--accept-unknown-result', action='store_true')
    legacy = commands.add_parser('legacy').add_subparsers(dest='action', required=True)
    for action in ('inspect', 'import-content'):
        cmd = legacy.add_parser(action)
        cmd.add_argument('--source', required=True, type=Path)
        if action == 'import-content':
            root_options(cmd)
            cmd.add_argument('--name', required=True)
    skills = commands.add_parser('skills').add_subparsers(dest='action', required=True)
    skills.add_parser('list')
    read = skills.add_parser('read')
    read.add_argument('name')
    for action in ('install', 'uninstall'):
        cmd = skills.add_parser(action)
        cmd.add_argument('--user-dir', required=True, type=Path)
    context = commands.add_parser('context-ir').add_subparsers(dest='action', required=True)
    for action in ('run', 'resume', 'review', 'derive', 'status', 'attach-task'):
        cmd = context.add_parser(action)
        root_options(cmd)
        cmd.add_argument('--plan')
        cmd.add_argument('--segment')
        cmd.add_argument('--operation')
        cmd.add_argument('--file', type=Path)
        cmd.add_argument('--confirm', action='store_true')
        cmd.add_argument('--retry-of')
        cmd.add_argument('--task')
        cmd.add_argument('--submit-only', action='store_true')
        cmd.add_argument('--max-polls', type=int, default=60)
        cmd.add_argument('--poll-ms', type=int, default=5000)
    return app


async def dispatch(args, services: Services) -> dict | list:
    from .application.story import import_story, initialize, load_story, replace_prompt
    from .credentials.config import credential, runtime_dir
    from .credentials.network import network
    from .persistence.files import read_json, read_stable
    from .providers.http import Http
    from .providers.metaso import Metaso
    from .providers.yiciyuang import Yiciyuang
    from .video.execution import ExecutionOptions, run_video
    from .video.planning import prepare
    command = args.command
    root = cast(Path, getattr(args, 'root', None))
    if command == 'init':
        story = initialize(root, args.name)
        return {'projectId': story['projectId'], 'revision': story['revision'], 'root': str(root.absolute())}
    if command == 'import':
        if args.draft:
            draft = read_json(args.draft)
            if not Path(draft['source']).is_absolute():
                draft['source'] = str(args.draft.parent / draft['source'])
        else:
            from .domain.text import normalize_text, utf16_length
            if not args.episode:
                raise AppError('INVALID_INPUT', '--episode is required with --file.')
            draft = {'episodeId': args.episode, 'kind': args.kind, 'source': str(args.file.absolute()), 'offsetEncoding': 'utf16',
                     'segments': [{'id': 's1', 'start': 0, 'end': utf16_length(normalize_text(read_stable(args.file))), 'duration': args.duration}]}
        story = import_story(root, draft, args.replace)
        return {'projectId': story['projectId'], 'revision': story['revision'], 'episodeId': draft['episodeId']}
    if command == 'assets':
        from .application.assets import inspect_assets, register_asset
        if args.action == 'list':
            return inspect_assets(root)
        if args.url:
            import uuid

            from .application.story import STATE
            from .media.inspect import MAX_IMAGE
            from .persistence.files import project_path
            http = Http(**network('metaso'))
            path = project_path(root, f'{STATE}/imports/{uuid.uuid4()}.bin')
            try:
                await http.download(args.url, path, limit=MAX_IMAGE, total=30, redirects=0)
                return register_asset(root, args.id, path, args.provenance, args.expected_sha256, url=args.url)
            finally:
                await http.close()
        return register_asset(root, args.id, args.file, args.provenance, args.expected_sha256)
    if command == 'prompts':
        return replace_prompt(root, args.episode, args.segment, args.file, args.expected_sha256, args.expected_prompt_hash,
                              read_json(args.narration_cues) if args.narration_cues else None)
    if command == 'auth' or (command == 'images' and args.action.startswith('auth-')):
        from .credentials.config import status
        from .credentials.connect import connect
        auth_provider = 'metaso' if command == 'auth' else 'images'
        return connect(auth_provider) if args.action in ('connect', 'auth-connect') else status(auth_provider, decrypt=getattr(args, 'decrypt', False))
    if command == 'plan':
        return prepare(root, [args.episode], workflow=args.workflow)
    if command in ('video', 'batch'):
        if args.action == 'register':
            from .video.capacity import Capacity
            return Capacity(runtime_dir()).register_existing(root)
        if args.action == 'plan' or not getattr(args, 'batch', None):
            if command == 'video' and not args.episodes and not args.selection:
                raise AppError('INVALID_SELECTION', 'Explicit episodes, selection or batch are required.')
            plan = prepare(root, args.episodes.split(',') if args.episodes else None,
                           read_json(args.selection) if args.selection else None, args.concurrency)
            batch_id = plan['batchId']
            if args.action == 'plan':
                return plan
            if args.expect_scope and args.expect_scope != plan['scopeHash']:
                raise AppError('SCOPE_CHANGED', 'Frozen scope differs from expected scope.')
            if args.action == 'execute' and args.confirm and not args.expect_scope:
                raise AppError('EXPECT_SCOPE_REQUIRED', 'video execute requires expected scope for selectors.')
        else:
            batch_id = args.batch
        if args.action == 'retry':
            from .video.retry import authorize_retry
            authorize_retry(root, batch_id, args.operation, args.confirm, args.accept_unknown_result)
        execute = args.confirm or args.action in ('resume', 'retry')
        provider = services.video_factory() if services.video_factory and execute else Metaso(Http(**network('metaso')), credential('metaso')) if execute else None
        try:
            options = services.execution_options or ExecutionOptions(max_polls=args.max_polls,
                poll_seconds=args.poll_ms / 1000, capacity_wait=args.capacity_wait_ms / 1000, capacity_poll=args.capacity_poll_ms / 1000)
            if not 1 <= options.max_polls <= 720 or not 0 <= options.poll_seconds <= 60 or not 0 <= options.capacity_wait <= 300 or not .001 <= options.capacity_poll <= 60:
                raise AppError('INVALID_INPUT', 'Polling/wait bounds are invalid.')
            result = await run_video(root, batch_id, provider=provider, runtime=runtime_dir() if execute else None,
                                     confirm=args.confirm, resume=args.action in ('resume', 'retry'), options=options,
                                     full_scope=command == 'batch' and args.action == 'run' and args.confirm)
            if getattr(args, 'verify_av', False):
                from .media.av import verify_delivery
                return await verify_delivery(root, result)
            return result
        finally:
            if provider:
                await provider.http.close()
    if command == 'images':
        from .images.workflow import collect_images, plan_images, prepare_images, run_images
        if args.action == 'prepare':
            return prepare_images(root, read_json(args.batch) if args.batch else None, args.preparation)
        if args.action == 'plan':
            return plan_images(root, assets=args.assets.split(',') if args.assets else None,
                episodes=args.episodes.split(',') if args.episodes else None, selected=read_json(args.selection) if args.selection else None,
                profile=read_json(args.profile) if args.profile else None, restart_of=args.restart_of)
        if args.action in ('collect', 'status'):
            plan_id = args.plan
            if args.preparation:
                from .images.collection import collect_preparation
                return collect_preparation(root, args.preparation)
            if not plan_id:
                raise AppError('INVALID_INPUT', 'Specify exact plan or preparation.')
            return collect_images(root, plan_id)
        if args.action in ('run', 'retry') and not args.confirm:
            raise AppError('AUTHORIZATION_REQUIRED', 'Explicit confirmation is required before image submission.')
        local = args.action in ('attach-result', 'resolve')
        provider = None if local else services.image_factory() if services.image_factory else Yiciyuang(Http(**network('images')), credential('images'))
        try:
            if args.action in ('recover', 'retry', 'attach-result', 'resolve'):
                from .images.recovery import recover_command
                return await recover_command(root, args, provider, runtime_dir())
            if not args.plan:
                raise AppError('INVALID_INPUT', 'Specify exact image plan.')
            assert provider is not None
            return await run_images(root, args.plan, provider=provider, runtime=runtime_dir(), confirm=args.confirm,
                                    resume=args.action == 'resume', accept_unknown=args.accept_unknown_result,
                                    capacity_wait=args.capacity_wait_ms/1000, capacity_poll=args.capacity_poll_ms/1000,
                                    checkpoint=services.image_checkpoint)
        finally:
            if provider:
                await provider.http.close()
    if command in ('status', 'doctor') and not getattr(args, 'remote', False):
        from .application.assets import inspect_assets
        from .video.store import find_jobs, load_job
        if getattr(args, 'operation', None):
            job = load_job(root, args.operation)
            return {k: v for k, v in job.items() if k not in ('resultUrl', 'hash', 'hashVersion')}
        story = load_story(root)
        return {'projectId': story['projectId'], 'revision': story['revision'], 'episodes': len(story['episodes']),
                'assets': inspect_assets(root), 'jobs': [{'operationId': j['operationId'], 'status': j['status'], 'taskId': j.get('taskId')} for j in find_jobs(root)]}
    if command in ('generate', 'resume', 'download', 'attach-task', 'status'):
        from .video.single import single_command
        options = services.execution_options or ExecutionOptions(max_polls=getattr(args, 'max_polls', 60),
                                                                 poll_seconds=getattr(args, 'poll_ms', 5000)/1000)
        if not 1 <= options.max_polls <= 720 or not 0 <= options.poll_seconds <= 60:
            raise AppError('INVALID_INPUT', 'Polling bounds are invalid.')
        execute = command != 'generate' or args.confirm
        provider = (services.video_factory() if services.video_factory else Metaso(Http(**network('metaso')), credential('metaso'))) if execute else None
        try:
            return await single_command(root, args, provider, runtime_dir(), options)
        finally:
            if provider:
                await provider.http.close()
    if command == 'legacy':
        from .application.legacy import import_content, inspect_legacy
        return inspect_legacy(args.source) if args.action == 'inspect' else import_content(args.source, args.root, args.name)
    if command == 'skills':
        from .application.skills import skills_command
        return skills_command(args)
    if command == 'context-ir':
        from .video.context_ir import ir_command
        if args.action == 'run' and not args.confirm:
            raise AppError('AUTHORIZATION_REQUIRED', 'Independent IR requires explicit confirmation.')
        provider = (services.video_factory() if services.video_factory else Metaso(Http(**network('metaso')), credential('metaso'))) if args.action in ('run', 'resume', 'attach-task') else None
        try:
            return await ir_command(root, args, provider)
        finally:
            if provider:
                await provider.http.close()
    raise AppError('INVALID_INPUT', 'Unknown command.')


def main(argv: list[str] | None = None, services: Services | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    # Version/help are parsed before heavy dependencies are imported.
    try:
        values = sys.argv[1:] if argv is None else argv
        flags = [v.split('=', 1)[0] for v in values if v.startswith('--')]
        if len(flags) != len(set(flags)):
            raise AppError('CLI_ARGUMENT', 'Duplicate options are forbidden.')
        args = parser().parse_args(values)
        result = asyncio.run(dispatch(args, services or Services()))
        if isinstance(result, dict) and 'workflow' in result and 'batchHash' in result and 'segments' in result:
            result = {k: v for k, v in result.items() if k != 'segments'} | {
                'segments': [{k: item[k] for k in ('episodeId', 'segmentId', 'inputHash', 'requestHash')} for item in result['segments']],
                'planPath': str(args.root.absolute() / '.metasocli-py' / 'batches' / result['batchId'] / 'plan.json')}
        if getattr(args, 'summary', False) and isinstance(result, dict):
            rows = result.get('items', [])
            result = {k: result[k] for k in ('planId', 'planHash', 'preparationId', 'status', 'complete', 'indexPath') if k in result} | {
                'itemCount': len(rows), 'counts': {status: sum(row.get('status', row.get('action')) == status for row in rows)
                    for status in {row.get('status', row.get('action', 'unknown')) for row in rows}}}
            if result.get('planId') and args.command == 'images':
                result['planPath'] = str(args.root.absolute()/'.metasocli-py/image-plans'/f'{result["planId"]}.json')
        from .telemetry.safe import redact
        print(json.dumps(redact(result), ensure_ascii=False, allow_nan=False))
        return 2 if isinstance(result, dict) and (result.get('phase') in ('partial', 'delivery_incomplete') or result.get('complete') is False) else 0
    except AppError as error:
        print(json.dumps({'error': {'code': error.code, 'message': error.message}}, ensure_ascii=False))
        return 2 if error.incomplete else 1
    except KeyboardInterrupt:
        print(json.dumps({'error': {'code': 'STOPPED', 'message': 'Stopped locally; accepted remote tasks may continue.'}}))
        return 2
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({'error': {'code': 'LOCAL_INPUT_OR_IO', 'message': 'Local input or I/O failed; preserve state for recovery.'}}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
