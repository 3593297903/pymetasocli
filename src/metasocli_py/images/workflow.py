import asyncio
import base64
import binascii
import re
import time
import uuid
from pathlib import Path

from pydantic import ValidationError

from ..application.assets import register_asset
from ..application.story import STATE, import_story, load_story, merge_import, normalize_import
from ..contracts.records import validate_record
from ..domain.errors import AppError
from ..media.inspect import image_info
from ..persistence.codec import digest, loads, sealed, sha256, verify
from ..persistence.files import (
    atomic_write,
    is_locked,
    lock,
    project_path,
    read_json,
    read_stable,
    write_json,
)
from ..providers.yiciyuang import Yiciyuang
from ..video.planning import now, selection
from .contracts import ImageJob, ImagePlan, ImageRun, Profile


class MeasuredSemaphore(asyncio.Semaphore):
    def __init__(self, limit: int):
        super().__init__(limit)
        self.active = self.peak = 0
        self.wait_ms = 0.0

    async def acquire(self):
        start = time.perf_counter()
        result = await super().acquire()
        self.wait_ms += (time.perf_counter()-start)*1000
        self.active += 1
        self.peak = max(self.peak, self.active)
        return result

    def release(self):
        self.active -= 1
        super().release()


def profile_value(value: dict | None) -> dict:
    try:
        return Profile.model_validate(value or {}).model_dump(exclude_none=True)
    except ValidationError:
        raise AppError('IMAGE_PROFILE', 'Invalid image profile fields or values.') from None


def image_jobs(root: Path) -> list[dict]:
    folder = project_path(root, f'{STATE}/image-jobs')
    plans: dict[str, dict] = {}
    return [load_image_job(root, path.stem, plans) for path in sorted(folder.glob('*.json'))] if folder.exists() else []


def load_image_job(root: Path, operation: str, plans: dict | None = None) -> dict:
    job = validate_record(ImageJob, verify(read_json(project_path(root, f'{STATE}/image-jobs/{operation}.json'))))
    cache = plans if plans is not None else {}
    if job['planId'] not in cache:
        cache[job['planId']] = load_plan(root, job['planId'])
    plan = cache[job['planId']]
    item = next((i for i in plan['items'] if i['assetId'] == job['assetId']), None)
    if (job['operationId'] != operation or job['projectId'] != plan['projectId'] or job['planHash'] != plan['planHash']
        or item is None or item['fingerprint'] != job['fingerprint'] or digest(job['input']) != job['requestHash']
        or digest({'fingerprint': job['fingerprint'], 'input': job['input']}) != job['inputHash']):
        raise AppError('IMAGE_JOB_IDENTITY', 'Image operation, request and frozen plan identities do not match.')
    request = job['input']
    if (any(request[k] != item[k] for k in ('promptPath', 'promptHash', 'size'))
        or [r['assetId'] for r in request['references']] != item['dependencies']
        or any(request[k] != plan['profile'][k] for k in ('provider', 'origin', 'model', 'quality', 'n', 'response_format'))):
        raise AppError('IMAGE_JOB_IDENTITY', 'Image request differs from its frozen recipe or profile.')
    return job


def validate_decisions(root: Path, entries: list, story: dict, scope: dict) -> None:
    from ..media import handoff
    decisions: dict[str, dict] = {}
    for entry in entries:
        request = handoff.validate_request(entry['request'])
        recipe = handoff.validate_recipe(entry['recipe'], request)
        handoff.validate_import_draft(entry['draft'], request, recipe)
        if sha256(entry['source'].encode('utf-8')) != entry['sourceHash']:
            raise AppError('IMAGE_PREPARATION_STALE', 'Prepared source hash changed.')
        for decision in recipe['assets']:
            identifier = decision['assetId']
            if identifier in decisions and decisions[identifier] != decision:
                raise AppError('IMAGE_HANDOFF_CONFLICT', 'Shared asset decisions differ between episodes.')
            decisions[identifier] = decision
    recipes = {a['recipe']['assetId']: a for a in story['assets']}
    required = list(scope.get('assets') or [])
    if not required:
        for eid, sid in selection(story, scope.get('episodes'), scope.get('selection')):
            segment = next(s for e in story['episodes'] if e['id'] == eid for s in e['segments'] if s['id'] == sid)
            required.extend(r['assetId'] for r in segment['references'])
    visited = set()
    while required:
        identifier = required.pop()
        if identifier in visited:
            continue
        visited.add(identifier)
        decision, asset = decisions.get(identifier), recipes.get(identifier)
        if decision is None or asset is None or decision['status'] == 'skipped_optional':
            raise AppError('IMAGE_HANDOFF_CONFLICT', 'Selected asset has no executable handoff decision.')
        if decision['status'] == 'blocked':
            raise AppError('IMAGE_PREPARATION_BLOCKED', 'Selected asset is blocked: ' + identifier)
        if decision['status'] == 'reused':
            media = asset['media']
            if not media or media['sha256'] != decision['contentSha256'] or media['path'] != decision['existingRelativePath'] or sha256(read_stable(project_path(root, media['path']))) != media['sha256']:
                raise AppError('IMAGE_PREPARATION_STALE', 'Reused image no longer matches its handoff decision.')
        elif asset['recipe']['prompt'] != decision['generationPrompt']:
            raise AppError('IMAGE_HANDOFF_CONFLICT', 'Generation prompt differs from its frozen recipe.')
        required.extend(asset['recipe']['dependencies'])


def save_job(root: Path, job: dict) -> None:
    with lock(project_path(root, f'{STATE}/story.lock')):
        write_json(project_path(root, f'{STATE}/image-jobs/{job["operationId"]}.json'), validate_record(ImageJob, sealed(job)))


def plan_images(root: Path, *, assets: list[str] | None = None, episodes: list[str] | None = None,
                selected: dict | None = None, profile: dict | None = None, restart_of: str | None = None,
                plan_id: str | None = None, before_write=None) -> dict:
    story, configured = load_story(root), profile_value(profile)
    recipes = {a['recipe']['assetId']: a for a in story['assets']}
    ids = list(assets or [])
    scope = []
    if not assets:
        scope = selection(story, episodes, selected)
        for eid, sid in scope:
            episode = next(e for e in story['episodes'] if e['id'] == eid)
            segment = next(s for s in episode['segments'] if s['id'] == sid)
            ids.extend(r['assetId'] for r in segment['references'])
    ordered, visited = [], set()
    def visit(asset_id):
        if asset_id in visited:
            return
        if asset_id not in recipes or recipes[asset_id]['recipe']['kind'] == 'narration':
            raise AppError('MISSING_RECIPE', 'Image scope requires declared image assets.')
        visited.add(asset_id)
        for dependency in recipes[asset_id]['recipe']['dependencies']:
            visit(dependency)
        ordered.append(asset_id)
    for asset_id in ids:
        visit(asset_id)
    if not ordered:
        raise AppError('IMAGE_SCOPE', 'No image assets selected.')
    historical = image_jobs(root)
    items = []
    for asset_id in ordered:
        asset = recipes[asset_id]
        recipe = asset['recipe']
        prompt = recipe['prompt'].encode('utf-8')
        prompt_hash = sha256(prompt)
        prompt_path = f'{STATE}/image-inputs/{prompt_hash}.txt'
        atomic_write(project_path(root, prompt_path), prompt)
        media = asset['media']
        reusable = False
        if media:
            reusable = sha256(read_stable(project_path(root, media['path']), configured['maxImageBytes'])) == media['sha256']
        size = configured['sizes'].get(asset_id, configured['firstFrameSize'] if recipe['kind'] == 'first_frame' else configured['boardSize'])
        fingerprint = digest({'assetId': asset_id, 'recipeHash': asset['recipeHash'], 'size': size,
                              'profile': configured, 'dependencies': [
                                  {'assetId': d, 'recipeHash': recipes[d]['recipeHash'],
                                   'mediaHash': recipes[d]['media']['sha256'] if recipes[d]['media'] else None}
                                  for d in recipe['dependencies']]})
        previous = next((j for j in reversed(historical) if j['assetId'] == asset_id and j['fingerprint'] == fingerprint), None)
        item = {'assetId': asset_id, 'kind': recipe['kind'], 'recipeHash': asset['recipeHash'],
                'promptPath': prompt_path, 'promptHash': prompt_hash, 'dependencies': recipe['dependencies'],
                'dependencyHashes': {d: recipes[d]['media']['sha256'] if recipes[d]['media'] else None for d in recipe['dependencies']},
                'targetHash': media['sha256'] if media else None, 'size': size, 'fingerprint': fingerprint,
                'action': 'reuse' if reusable else 'recover' if previous and not restart_of else 'generate'}
        if previous:
            item['retryOf' if restart_of else 'operationId'] = previous['operationId']
        if item['action'] == 'generate':
            width, height = map(int, size.split('x'))
            pixels = re.findall(r'\b(\d{3,4})\s*[x×]\s*(\d{3,4})\b', recipe['prompt'])
            incompatible = ((re.search(r'\b4K\b', recipe['prompt'], re.I) and max(width, height) < 4096)
                or (re.search(r'\b2K\b', recipe['prompt'], re.I) and max(width, height) < 2048)
                or any((int(w), int(h)) != (width, height) for w, h in pixels)
                or (recipe['kind'] != 'first_frame' and width < height))
            if recipe['kind'] == 'first_frame' and asset_id not in configured['sizes']:
                incompatible = incompatible or any(
                    s['parameters']['ratio'] not in ('9:16', 'adaptive')
                    for e in story['episodes'] for s in e['segments']
                    if (e['id'], s['id']) in scope and any(r['assetId'] == asset_id for r in s['references']))
            if incompatible:
                item.update(action='blocked', blocker={'code': 'IMAGE_SPECIFICATION',
                    'message': 'Prompt specification conflicts with configured size; choose an explicit supported profile size.'})
        items.append(item)
    content = {'projectId': story['projectId'], 'items': items, 'profile': configured, 'scope': scope, 'restartOf': restart_of}
    folder = project_path(root, f'{STATE}/image-plans')
    if folder.exists() and plan_id is None:
        for file in folder.glob('*.json'):
            prior = verify(read_json(file), 'planHash')
            if prior['contentHash'] == digest(content):
                return prior
    plan = sealed({**content, 'schemaVersion': 1, 'planId': plan_id or str(uuid.uuid4()), 'createdAt': now(),
                   'contentHash': digest(content)}, 'planHash')
    if before_write:
        before_write(plan)
    write_json(project_path(root, f'{STATE}/image-plans/{plan["planId"]}.json'), plan)
    return plan


def load_plan(root: Path, plan_id: str) -> dict:
    plan = verify(read_json(project_path(root, f'{STATE}/image-plans/{plan_id}.json')), 'planHash')
    validate_record(ImagePlan, plan)
    if plan['planId'] != plan_id or plan['projectId'] != load_story(root)['projectId']:
        raise AppError('IMAGE_PLAN_IDENTITY', 'Image plan belongs to another story.')
    return plan


def prepare_images(root: Path, batch: dict | None = None, preparation: str | None = None) -> dict:
    from ..media import handoff
    if (batch is None) == (preparation is None):
        raise AppError('INVALID_INPUT', 'Choose batch input or a preparation ID.')
    folder = project_path(root, f'{STATE}/image-preparations')
    record: dict | None
    if preparation:
        record = verify(read_json(project_path(folder, f'{preparation}/input.json')))
    else:
        assert batch is not None
        if set(batch) - {'schemaVersion', 'projectId', 'entries', 'scope', 'profilePath', 'restartOf'} or batch.get('schemaVersion') != 1 or batch.get('projectId') != load_story(root)['projectId']:
            raise AppError('IMAGE_PREPARATION', 'Invalid batch identity or fields.')
        inputs = []
        projected = load_story(root)
        seen = set()
        for entry in batch['entries']:
            if set(entry) - {'episodeId', 'draftPath', 'requestPath', 'recipePath', 'replace'}:
                raise AppError('IMAGE_PREPARATION', 'Unknown entry field.')
            draft = read_json(project_path(root, entry['draftPath']))
            if draft['episodeId'] != entry['episodeId'] or entry['episodeId'] in seen:
                raise AppError('IMAGE_PREPARATION', 'Duplicate or mismatched episode binding.')
            seen.add(entry['episodeId'])
            request = handoff.validate_request(read_json(project_path(root, entry['requestPath'])))
            recipe = handoff.validate_recipe(read_json(project_path(root, entry['recipePath'])), request)
            handoff.validate_import_draft(draft, request, recipe)
            source = read_stable(project_path(root, draft['source']) if not Path(draft['source']).is_absolute() else Path(draft['source']))
            normalized, _, _, episode = normalize_import(draft, source)
            previous = next((e for e in projected['episodes'] if e['id'] == entry['episodeId']), None)
            projected = merge_import(projected, normalized, episode, entry.get('replace', False))
            for decision in recipe['assets']:
                if decision['status'] == 'planned':
                    selected_recipe = next(a['recipe'] for a in projected['assets'] if a['recipe']['assetId'] == decision['assetId'])
                    if selected_recipe['prompt'] != decision['generationPrompt']:
                        raise AppError('IMAGE_HANDOFF_CONFLICT', 'Finalize type-specific denoise before freezing recipe/draft hashes.')
            inputs.append({'episodeId': entry['episodeId'], 'draft': draft, 'request': request,
                           'recipe': recipe, 'source': source.decode('utf-8'), 'sourceHash': sha256(source),
                           'previousEpisodeHash': digest(previous) if previous else None,
                           'expectedEpisode': episode, 'sourceBasename': Path(draft['source']).name,
                           'replace': entry.get('replace', False)})
        profile = read_json(project_path(root, batch['profilePath'])) if batch.get('profilePath') else None
        validate_decisions(root, inputs, projected, batch['scope'])
        content_hash = digest({'batch': batch, 'inputs': inputs, 'profile': profile})
        prior = []
        if folder.exists():
            prior = [verify(read_json(p)) for p in folder.glob('*/input.json')]
        record = next((r for r in prior if r['contentHash'] == content_hash), None)
        if record is None:
            preparation = str(uuid.uuid4())
            record = sealed({'preparationId': preparation, 'planId': str(uuid.uuid4()), 'projectId': batch['projectId'], 'contentHash': content_hash,
                             'entries': inputs, 'scope': batch['scope'], 'profile': profile, 'restartOf': batch.get('restartOf')})
            write_json(project_path(folder, f'{preparation}/input.json'), record)
    preparation = record['preparationId']
    statefile = project_path(folder, f'{preparation}/state.json')
    with lock(project_path(folder, f'{preparation}/preparation.lock'), timeout=0):
        state: dict = verify(read_json(statefile)) if statefile.exists() else {'imported': {}, 'status': 'preparing'}
        projected = load_story(root)
        for entry in record['entries']:
            normalized, _, _, episode = normalize_import(entry['draft'], entry['source'].encode('utf-8'))
            projected = merge_import(projected, normalized, episode, entry['replace'])
        validate_decisions(root, record['entries'], projected, record['scope'])
        for index, entry in enumerate(record['entries']):
            story = load_story(root)
            current = next((e for e in story['episodes'] if e['id'] == entry['episodeId']), None)
            if entry['episodeId'] in state['imported']:
                if current is None or digest(current) != state['imported'][entry['episodeId']]:
                    raise AppError('IMAGE_PREPARATION_STALE', 'Imported episode changed; preserve current edits.')
                continue
            sourcefile = project_path(folder, f'{preparation}/sources/{index}/{entry["sourceBasename"]}')
            source = entry['source'].encode('utf-8')
            if sha256(source) != entry['sourceHash']:
                raise AppError('RECORD_INTEGRITY', 'Prepared source bytes changed.')
            atomic_write(sourcefile, source)
            draft = {**entry['draft'], 'source': str(sourcefile)}
            story = import_story(root, draft, entry['replace'], entry['previousEpisodeHash'], True)
            episode = next(e for e in story['episodes'] if e['id'] == entry['episodeId'])
            state['imported'][entry['episodeId']] = digest(episode)
            write_json(statefile, sealed(state))
        intentfile = project_path(folder, f'{preparation}/plan-intent.json')
        if intentfile.exists():
            plan = verify(read_json(intentfile), 'planHash')
            write_json(project_path(root, f'{STATE}/image-plans/{plan["planId"]}.json'), plan)
        else:
            scope = record['scope']
            plan = plan_images(root, assets=scope.get('assets'), episodes=scope.get('episodes'), selected=scope.get('selection'),
                               profile=record['profile'], restart_of=record['restartOf'], plan_id=record['planId'],
                               before_write=lambda p: write_json(intentfile, p))
        state.update(status='ready', planId=plan['planId'])
        write_json(statefile, sealed(state))
    return {'preparationId': preparation, 'planId': plan['planId'], 'status': 'ready', 'importedEpisodes': list(state['imported'])}


def assert_item(root: Path, item: dict) -> dict:
    asset = next((a for a in load_story(root)['assets'] if a['recipe']['assetId'] == item['assetId']), None)
    if asset is None or asset['recipeHash'] != item['recipeHash']:
        raise AppError('IMAGE_PLAN_STALE', 'Frozen recipe changed.')
    current = asset['media']['sha256'] if asset['media'] else None
    if current != item['targetHash']:
        raise AppError('IMAGE_SUPERSEDED', 'Target selected media changed after planning.')
    return asset


def effective_input(root: Path, item: dict, profile: dict) -> dict:
    assert_item(root, item)
    story = load_story(root)
    references = []
    for asset_id in item['dependencies']:
        asset = next(a for a in story['assets'] if a['recipe']['assetId'] == asset_id)
        media = asset['media']
        if media is None:
            raise AppError('IMAGE_DEPENDENCY', 'Image dependency has not been registered.')
        if item['dependencyHashes'][asset_id] is not None and item['dependencyHashes'][asset_id] != media['sha256']:
            raise AppError('IMAGE_PLAN_STALE', 'Frozen reference selection changed.')
        data = read_stable(project_path(root, media['path']), profile['maxImageBytes'])
        if sha256(data) != media['sha256']:
            raise AppError('IMAGE_INPUT_CHANGED', 'Dependency bytes changed.')
        path = f'{STATE}/image-inputs/{media["sha256"]}.bin'
        atomic_write(project_path(root, path), data)
        references.append({'assetId': asset_id, 'path': path, 'sha256': media['sha256'], 'mime': media['mime']})
    return {'provider': 'yiciyuang', 'origin': profile['origin'],
            'route': '/v1/images/edits' if references else '/v1/images/generations',
            'model': profile['model'], 'quality': profile['quality'], 'size': item['size'], 'n': 1,
            'response_format': profile['response_format'], 'promptPath': item['promptPath'],
            'promptHash': item['promptHash'], 'references': references}


PREPARED_PROTOCOL = 'prepared-before-admission-v1'


def unsent_prepared(job: dict) -> bool:
    return job.get('submissionProtocol') == PREPARED_PROTOCOL and job['status'] == 'prepared'


def authorization_hash(run: dict) -> str:
    return digest({k: run[k] for k in ('planId', 'planHash', 'authorizedAt', 'runtimeRoot', 'items')})


def prepared_proof(root: Path, job: dict, runtime: Path, cache=None) -> dict:
    """Positive persisted protocol proof, not an inference from missing receipts."""
    plans = {job['planId']: cache.plan(root, job['planId'])} if cache is not None else None
    saved = load_image_job(root, job['operationId'], plans)
    if not unsent_prepared(saved) or any(saved.get(k) != job.get(k) for k in (
        'operationId', 'projectId', 'planId', 'planHash', 'requestHash', 'inputHash', 'authorizationHash')):
        raise AppError('IMAGE_PREPARED_IDENTITY', 'Prepared operation identity or protocol differs.')
    runpath = project_path(root, f'{STATE}/image-runs/{job["planId"]}.json')
    run = cache.run(runpath) if cache is not None else validate_record(ImageRun, verify(read_json(runpath)))
    if (run['planId'] != job['planId'] or run['planHash'] != job['planHash']
        or run['runtimeRoot'] != str(runtime.absolute()).casefold()
        or run['items'].get(job['assetId']) != job['operationId']
        or authorization_hash(run) != saved['authorizationHash'] or run.get('replacementPlanId')):
        raise AppError('IMAGE_PREPARED_IDENTITY', 'Prepared operation lacks its original frozen authorization.')
    if project_path(root, f'{STATE}/image-receipts/{job["operationId"]}').exists():
        raise AppError('IMAGE_SUBMISSION_EVIDENCE', 'Prepared operation has possible submission evidence; preserve it.')
    return saved


class Quota:
    def __init__(self, runtime: Path, profile: dict, root: Path):
        self.folder = project_path(runtime, 'images/' + profile['quotaGroup'])
        self.profile = profile
        self.root = str(root.absolute()).casefold()
        self.runtime = runtime
        self.owner = str(project_path(root, f'{STATE}/submission.lock'))
        self.diagnostics: list[dict] = []
        from .proof_cache import PreparedProofCache
        self.proof_cache = PreparedProofCache()

    def read(self) -> dict:
        path, marker = self.folder / 'ledger.json', self.folder / 'owner.json'
        if marker.exists() and not path.exists():
            raise AppError('IMAGE_LEDGER_MISSING', 'Image quota ledger is missing; preserve unresolved evidence.')
        if path.exists() and (not marker.exists() or read_json(marker) != {'owner': 'metasocli-py-images', 'schemaVersion': 1}):
            raise AppError('IMAGE_LEDGER_OWNER', 'Image quota owner marker is missing or invalid.')
        data = verify(read_json(path)) if path.exists() else {'jobs': {}}
        if set(data) - {'jobs', 'hash', 'hashVersion'} or not isinstance(data['jobs'], dict):
            raise AppError('LEDGER_CORRUPT', 'Invalid image shared ledger.')
        return data

    def save(self, data: dict) -> None:
        marker = self.folder / 'owner.json'
        if not marker.exists():
            write_json(marker, {'owner': 'metasocli-py-images', 'schemaVersion': 1})
        write_json(self.folder / 'ledger.json', sealed(data))

    @staticmethod
    def held(slot: dict) -> bool:
        return slot.get('admissionState') != 'released' and slot['status'] in ('prepared', 'submitting', 'submit_unknown', 'response_saved')

    def identity(self, slot: dict, job: dict) -> None:
        if slot['root'] != self.root or any(slot.get(k) != job.get(k) for k in ('operationId', 'projectId', 'requestHash')):
            raise AppError('IMAGE_LEDGER_CONFLICT', 'Image quota operation identity differs.')
        if job.get('submissionProtocol') and any(slot.get(k) != job.get(k) for k in (
            'submissionProtocol', 'planId', 'planHash', 'inputHash', 'authorizationHash')):
            raise AppError('IMAGE_LEDGER_CONFLICT', 'Image quota authorization identity differs.')

    def repair_prepared(self) -> None:
        with lock(self.folder / 'ledger.lock'):
            snapshot = list(self.read()['jobs'].values())
        for slot in snapshot:
            if slot['root'] == self.root or not self.held(slot) or not unsent_prepared(slot):
                continue
            source = Path(slot['root'])
            owner = project_path(source, f'{STATE}/submission.lock')
            if str(owner).casefold() != str(slot.get('owner', '')).casefold():
                continue
            try:
                # Claim the exited owner's stable lease before inspecting source.
                # Holding it through revalidation prevents a restart/exit ABA race.
                with lock(owner, timeout=0):
                    job = load_image_job(source, slot['operationId'])
                    proof = prepared_proof(source, job, self.runtime)
                    if any(slot.get(k) != proof.get(k) for k in (
                        'projectId', 'requestHash', 'inputHash', 'planId', 'planHash', 'authorizationHash')):
                        continue
                    with lock(self.folder / 'ledger.lock'):
                        data = self.read()
                        current = data['jobs'].get(slot['operationId'])
                        if current != slot:
                            continue
                        current.update(admissionState='released', version=current.get('version', 0)+1)
                        current.setdefault('audit', []).append({'reason': 'owner_exited_proven_unsent',
                            'operationId': slot['operationId'], 'preparedHash': proof['hash'], 'at': now()})
                        self.save(data)
            except (AppError, OSError):
                # No file, old protocol, live owner or conflicting evidence is NOT
                # proof of non-submission. Its held reservation remains untouched.
                continue

    def update(self, job: dict, *, reserve: bool = False) -> bool:
        accepted = self._update_once(job, reserve=reserve)
        if accepted or not reserve:
            return accepted
        # Reconcile only after an actual quota obstruction, outside the ledger lock.
        self.repair_prepared()
        return self._update_once(job, reserve=True)

    def _update_once(self, job: dict, *, reserve: bool = False) -> bool:
        if reserve:
            prepared_proof(Path(self.root), job, self.runtime, self.proof_cache)
            if not is_locked(Path(self.owner)):
                raise AppError('IMAGE_QUOTA_OWNER', 'Admission requires the story submission lease.')
        with lock(self.folder / 'ledger.lock'):
            data = self.read()
            for operation, existing in data['jobs'].items():
                if existing['operationId'] != operation or (existing['projectId'] == job['projectId'] and existing['root'] != self.root) or (existing['root'] == self.root and existing['projectId'] != job['projectId']):
                    raise AppError('IMAGE_LEDGER_CONFLICT', 'Shared image identity belongs to another directory.')
            limits = self.profile.get('providerLimits', {})
            previous = data['jobs'].get(job['operationId'])
            if previous:
                self.identity(previous, job)
            if reserve:
                if previous:
                    if not unsent_prepared(previous):
                        raise AppError('IMAGE_SUBMISSION_EVIDENCE', 'Existing reservation may have submitted; recover its result.')
                    if self.held(previous):
                        return True
                held = [j for j in data['jobs'].values() if self.held(j)]
                recent = [j for j in data['jobs'].values() if time.time() - j.get('admittedEpoch', j.get('sentEpoch', 0)) < 60]
                relevant_ids = {j['operationId'] for j in held} | {j['operationId'] for j in recent}
                known = [limits, *[j.get('limits', {}) for j in data['jobs'].values() if j['operationId'] in relevant_ids]]
                concurrent = min((v['concurrent'] for v in known if v.get('concurrent')), default=float('inf'))
                rpm = min((v['rpm'] for v in known if v.get('rpm')), default=float('inf'))
                if len(held) >= concurrent or len(recent) + (0 if previous in recent else 1) > rpm:
                    self.diagnostics = [{'operationId': j['operationId'], 'status': j['status'],
                        'code': 'IMAGE_QUOTA_HELD', 'provenPreparedProtocol': j.get('submissionProtocol') == PREPARED_PROTOCOL,
                        'message': 'Reservation retained: live owner or possible submission; missing files alone do not prove an unsent request.'}
                        for j in held]
                    if len(recent) + (0 if previous in recent else 1) > rpm:
                        self.diagnostics.append({'code': 'IMAGE_RPM_LIMIT', 'message': 'Admission RPM budget is prepaid; wait for its existing window.'})
                    return False
            elif unsent_prepared(job):
                # The recover command cannot acquire or revive a reservation.
                return True
            slot = dict(previous or {})
            slot.update({k: job[k] for k in ('operationId', 'projectId', 'status', 'requestHash', 'sentEpoch',
                'submissionProtocol', 'planId', 'planHash', 'inputHash', 'authorizationHash') if k in job})
            slot.update(root=self.root, owner=self.owner, limits=limits, version=slot.get('version', 0)+1)
            if reserve:
                # A released reservation must re-enter admission. Reuse a still
                # valid prepaid token, otherwise charge the new window exactly once.
                prior_epoch = slot.get('admittedEpoch')
                if previous not in recent:
                    slot['admittedEpoch'] = time.time()
                slot['admissionState'] = 'held'
                slot.setdefault('audit', []).append({'reason': 'prepared_admission', 'operationId': job['operationId'],
                    'admittedEpoch': slot['admittedEpoch'], 'previousAdmittedEpoch': prior_epoch, 'at': now()})
            else:
                slot['admissionState'] = 'held' if job['status'] in ('submitting', 'submit_unknown', 'response_saved') else 'released'
            data['jobs'][job['operationId']] = slot
            self.save(data)
            return True

    def start_submission(self, job: dict) -> None:
        prepared_proof(Path(self.root), job, self.runtime, self.proof_cache)
        with lock(self.folder / 'ledger.lock'):
            data = self.read()
            slot = data['jobs'].get(job['operationId'])
            if slot is None:
                raise AppError('IMAGE_QUOTA_OWNER', 'Prepared operation has no admission.')
            self.identity(slot, job)
            if not self.held(slot) or not unsent_prepared(slot) or str(slot.get('owner', '')).casefold() != self.owner.casefold() or not is_locked(Path(self.owner)):
                raise AppError('IMAGE_QUOTA_OWNER', 'Prepared admission is no longer owned by this run.')
            job.update(status='submitting', sentEpoch=time.time(), requestStartedAt=now())
            job.setdefault('timings', {})['intent'] = time.perf_counter()
            save_job(Path(self.root), job)
            slot.update(status='submitting', sentEpoch=job['sentEpoch'], version=slot['version']+1)
            self.save(data)

    def assert_submission(self, job: dict) -> None:
        with lock(self.folder / 'ledger.lock'):
            slot = self.read()['jobs'].get(job['operationId'])
            if slot is None:
                raise AppError('IMAGE_QUOTA_OWNER', 'Submission admission is missing.')
            self.identity(slot, job)
            if (not self.held(slot) or slot['status'] != 'submitting' or str(slot.get('owner', '')).casefold() != self.owner.casefold()
                or slot.get('sentEpoch') != job.get('sentEpoch') or not is_locked(Path(self.owner))):
                raise AppError('IMAGE_QUOTA_OWNER', 'Submission admission ownership changed.')


async def recover_image(root: Path, job: dict, item: dict, profile: dict, provider: Yiciyuang,
                        decode: asyncio.Semaphore, downloads: asyncio.Semaphore,
                        register: asyncio.Semaphore, checkpoint=lambda _point, _job: None) -> dict:
    folder = project_path(root, f'{STATE}/image-receipts/{job["operationId"]}')
    complete = folder / 'complete.json'
    if unsent_prepared(job):
        if folder.exists():
            raise AppError('IMAGE_SUBMISSION_EVIDENCE', 'Prepared operation has conflicting submission evidence.')
        return job
    if not complete.exists():
        if job['status'] in ('submitting', 'prepared'):
            job['status'] = 'submit_unknown'
            save_job(root, job)
        return job
    async with decode:
        job.setdefault('timings', {})['decodeStart'] = time.perf_counter()
        proof = verify(read_json(complete))
        raw = await asyncio.to_thread(read_stable, folder / 'response.bin', profile['maxResponseBytes'])
        if proof['operationId'] != job['operationId'] or proof['requestHash'] != job['requestHash'] or proof['sha256'] != sha256(raw) or proof['bytes'] != len(raw):
            raise AppError('IMAGE_RECEIPT_IDENTITY', 'Complete response evidence mismatch.')
        if proof['httpStatus'] != 200:
            job['status'] = 'rejected' if proof['httpStatus'] in (401, 402, 403, 429) else 'submit_unknown'
            job['error'] = {'code': 'IMAGE_HTTP', 'message': f'Provider returned HTTP {proof["httpStatus"]}.'}
            save_job(root, job)
            return job
        response = await asyncio.to_thread(loads, raw, limit=profile['maxResponseBytes'])
        del raw
        if not isinstance(response, dict) or not isinstance(response.get('data'), list) or len(response['data']) != 1:
            raise AppError('IMAGE_RESPONSE_CONTRACT', 'Expected exactly one image response item.')
        output = response['data'][0]
        if not isinstance(output, dict) or bool(output.get('url')) == bool(output.get('b64_json')):
            raise AppError('IMAGE_RESPONSE_CONTRACT', 'Expected one URL or Base64 result.')
        if len(str(output.get('revised_prompt', '')).encode('utf-8')) > 128000 or len(str(response.get('usage', '')).encode('utf-8')) > 16384:
            raise AppError('IMAGE_RESPONSE_CONTRACT', 'Response metadata exceeds limits.')
        staged_relative = f'{STATE}/drafts/assets/{job["operationId"]}/result.image'
        staged = project_path(root, staged_relative)
        url = output.get('url')
        if not url:
            try:
                data = await asyncio.to_thread(base64.b64decode, output['b64_json'], validate=True)
            except (ValueError, binascii.Error, TypeError):
                raise AppError('IMAGE_RESPONSE_CONTRACT', 'Invalid Base64 image.') from None
            if len(data) > profile['maxImageBytes']:
                raise AppError('IMAGE_LIMIT', 'Decoded image exceeds limit.')
            await asyncio.to_thread(atomic_write, staged, data)
        job['reportedModel'] = response.get('model')
        if job['reportedModel'] is not None and (not isinstance(job['reportedModel'], str) or len(job['reportedModel']) > 200):
            raise AppError('IMAGE_RESPONSE_CONTRACT', 'Invalid reported model metadata.')
        write_json(folder / 'receipt.json', sealed({'operationId': job['operationId'], 'requestHash': job['requestHash'],
            'bodyHash': proof['sha256'], 'requestedModel': job['input']['model'], 'reportedModel': job['reportedModel'],
            'receiptSavedAt': now(), **({'url': url} if url else {})}))
        job['status'] = 'received'
        if url:
            job['resultUrl'] = url
        save_job(root, job)
        del response, output
        job['timings']['decodeComplete'] = time.perf_counter()
    if url:
        async with downloads:
            job['timings']['downloadStart'] = time.perf_counter()
            await provider.http.download(url, staged, limit=profile['maxImageBytes'], redirects=0)
            job['timings']['downloadComplete'] = time.perf_counter()
    async with decode:
        data = await asyncio.to_thread(read_stable, staged, profile['maxImageBytes'])
        info = await asyncio.to_thread(image_info, data)
        if f'{info["width"]}x{info["height"]}' != item['size']:
            raise AppError('IMAGE_DIMENSIONS', 'Returned dimensions differ from the requested size.')
        job['result'] = {'path': staged_relative, **info, 'sha256': sha256(data), 'bytes': len(data)}
        del data
        job['status'] = 'downloaded'
        save_job(root, job)
    async with register, decode:
        await asyncio.to_thread(register_asset, root, item['assetId'], staged, 'imagegen',
                                job['result']['sha256'], item['targetHash'], True, item['recipeHash'], job['input']['references'])
        checkpoint('image-after-register', job)
        job['status'] = 'registered'
        job.pop('error', None)
        job['registeredAt'] = now()
        job['timings']['registered'] = time.perf_counter()
        save_job(root, job)
        save_execution(root, job)
    return job


def save_execution(root: Path, job: dict) -> None:
    folder = project_path(root, f'{STATE}/image-receipts/{job["operationId"]}')
    job_path = f'{STATE}/image-jobs/{job["operationId"]}.json'
    receipt_path = f'{STATE}/image-receipts/{job["operationId"]}/receipt.json'
    has_receipt = project_path(root, receipt_path).exists()
    write_json(folder / 'execution.json', sealed({**{k: job[k] for k in ('operationId', 'assetId', 'requestHash', 'inputHash', 'planId', 'planHash')},
        'schemaVersion': 1, 'provider': 'yiciyuang', 'requestedModel': job['input']['model'], 'reportedModel': job.get('reportedModel'),
        'requestedSize': job['input']['size'], 'width': job['result']['width'], 'height': job['result']['height'],
        'jobPath': job_path, 'jobSha256': sha256(read_stable(project_path(root, job_path))),
        'receiptPath': receipt_path if has_receipt else None,
        'receiptSha256': sha256(read_stable(project_path(root, receipt_path))) if has_receipt else None,
        'recoveredManually': job.get('recoveredManually', False)}))


async def run_images(root: Path, plan_id: str, *, provider: Yiciyuang, runtime: Path,
                     confirm=False, resume=False, accept_unknown=False, capacity_wait: float = 30, capacity_poll: float = .25,
                     checkpoint=lambda _point, _job: None) -> dict:
    if not 0 <= capacity_wait <= 300 or not .01 <= capacity_poll <= 60:
        raise AppError('INVALID_INPUT', 'Invalid image capacity wait budget.')
    plan = load_plan(root, plan_id)
    profile = plan['profile']
    runpath = project_path(root, f'{STATE}/image-runs/{plan_id}.json')
    with lock(project_path(root, f'{STATE}/submission.lock'), timeout=0):
        run = verify(read_json(runpath)) if runpath.exists() else None
        if run:
            validate_record(ImageRun, run)
        if run and run['planHash'] != plan['planHash']:
            raise AppError('AUTHORIZATION_IDENTITY', 'Image authorization mismatch.')
        if run and run.get('runtimeRoot') != str(runtime.absolute()).casefold():
            raise AppError('RUNTIME_CONFLICT', 'Resume must use the original image quota runtime.')
        if run is None and not confirm:
            raise AppError('AUTHORIZATION_REQUIRED', 'Confirm frozen image scope before submission.')
        new_items = [i for i in plan['items'] if i['action'] == 'generate']
        from ..application.stages import new_submission
        accepted: set[str] = set()
        ancestor = plan.get('restartOf')
        visited = set()
        while ancestor:
            if ancestor in visited:
                raise AppError('RETRY_ANCESTRY', 'Retry ancestry cycle.')
            visited.add(ancestor)
            prior = load_plan(root, ancestor)
            original_jobs = [j for j in image_jobs(root) if j['planId'] == ancestor]
            if any(j['status'] in ('submitting', 'response_saved', 'received', 'downloaded') for j in original_jobs):
                raise AppError('IMAGE_RESTART_RECOVERY_REQUIRED', 'Recover complete or in-flight original results before another attempt.')
            accepted.update(j['operationId'] for j in original_jobs)
            ancestor = prior.get('restartOf')
        # Recovery of existing operations never creates a new request.
        existing_ids = set((run or {}).get('items', {}).values())
        if any(i['assetId'] not in (run or {}).get('items', {}) for i in new_items):
            new_submission(root, 'images', accepted | existing_ids)
        from .resources import preflight
        resources = preflight(root, len(new_items), profile)
        limits = profile.get('providerLimits', {})
        if limits.get('batch') and len(new_items) > limits['batch']:
            raise AppError('IMAGE_BATCH_LIMIT', 'Frozen request count exceeds known provider batch limit.')
        if run is None:
            if plan.get('restartOf'):
                if not accept_unknown:
                    raise AppError('UNKNOWN_ACCEPTANCE_REQUIRED', 'One new attempt requires explicit unknown-result acceptance.')
                oldfile = project_path(root, f'{STATE}/image-runs/{plan["restartOf"]}.json')
                old = verify(read_json(oldfile))
                if old.get('replacementPlanId') not in (None, plan_id):
                    raise AppError('RETRY_ALREADY_AUTHORIZED', 'Previous image plan already has one authorized successor.')
                old['replacementPlanId'] = plan_id
                write_json(oldfile, sealed(old))
            reserved = {i['assetId']: str(uuid.uuid4()) if i['action'] == 'generate' else i.get('operationId')
                        for i in plan['items'] if i['action'] in ('generate', 'recover')}
            run = {'planId': plan_id, 'planHash': plan['planHash'], 'authorizedAt': now(), 'items': reserved,
                   'runtimeRoot': str(runtime.absolute()).casefold(),
                   'maxRequests': len(new_items), 'acceptUnknown': bool(accept_unknown), 'resources': resources}
            write_json(runpath, sealed(run))
        if run.get('replacementPlanId'):
            raise AppError('IMAGE_SUPERSEDED', 'This plan was superseded by its authorized successor.')
        quota = Quota(runtime, profile, root)
        decode, downloads, register = MeasuredSemaphore(2), MeasuredSemaphore(2), MeasuredSemaphore(1)
        done, pending = set(), list(plan['items'])
        produced: dict[str, str] = {}
        tasks: dict[asyncio.Task, dict] = {}
        jobs_by_id = {j['operationId']: j for j in image_jobs(root)}
        stop_new = False
        waiting_since = None
        changed = asyncio.Event()
        async def one(item, job, submit):
            nonlocal stop_new
            try:
                if submit:
                    checkpoint('image-after-intent', job)
                    quota.assert_submission(job)
                    job['timings']['send'] = time.perf_counter()
                    await provider.create(root, job, profile, project_path(root, f'{STATE}/image-receipts/{job["operationId"]}'))
                    job['timings']['responseComplete'] = time.perf_counter()
                    checkpoint('image-response-complete', job)
                    job['status'] = 'response_saved'
                    save_job(root, job)
                await recover_image(root, job, item, profile, provider, decode, downloads, register, checkpoint)
            except (AppError, OSError) as error:
                if job['status'] == 'submitting':
                    job['status'] = 'submit_unknown'
                job['error'] = {'code': error.code if isinstance(error, AppError) else 'LOCAL_IO',
                                'message': error.message if isinstance(error, AppError) else 'Local image I/O failed.'}
                save_job(root, job)
            except asyncio.CancelledError:
                if job['status'] == 'submitting':
                    job['status'] = 'submit_unknown'
                    save_job(root, job)
                raise
            finally:
                if 'sentEpoch' in job:
                    quota.update(job)
                if job['status'] == 'registered':
                    done.add(item['assetId'])
                    produced[item['assetId']] = job['result']['sha256']
                elif job['status'] in ('submit_unknown', 'rejected', 'failed'):
                    stop_new = True
                changed.set()
        async def pump():
            nonlocal stop_new, waiting_since
            while pending or tasks:
                launched = False
                capacity_blocked = False
                for item in list(pending):
                    if item['action'] == 'blocked':
                        run.setdefault('blockers', {})[item['assetId']] = item['blocker']
                        write_json(runpath, sealed(run))
                        pending.remove(item)
                        continue
                    if item['action'] == 'reuse':
                        assert_item(root, item)
                        done.add(item['assetId'])
                        pending.remove(item)
                        continue
                    operation = run['items'].get(item['assetId']) or item.get('operationId')
                    job = jobs_by_id.get(operation) if operation else None
                    if job and not unsent_prepared(job):
                        pending.remove(item)
                        if job['status'] == 'registered':
                            done.add(item['assetId'])
                            produced[item['assetId']] = job['result']['sha256']
                        else:
                            tasks[asyncio.create_task(one(item, job, False))] = item
                        continue
                    if stop_new or not all(d in done for d in item['dependencies']):
                        continue
                    if operation and project_path(root, f'{STATE}/image-receipts/{operation}').exists():
                        raise AppError('IMAGE_JOB_MISSING', 'Missing image job has submission evidence; restore it without sending.')
                    # A dependency absent at planning must come from this run's exact
                    # producer. A manual selection made while it ran is not equivalent.
                    effective = {**item, 'dependencyHashes': {
                        d: h if h is not None else produced.get(d)
                        for d, h in item['dependencyHashes'].items()}}
                    try:
                        if any(h is None for h in effective['dependencyHashes'].values()):
                            raise AppError('IMAGE_DEPENDENCY', 'The planned producer has no registered result.')
                        request = effective_input(root, effective, profile)
                        if sha256(read_stable(project_path(root, request['promptPath']))) != request['promptHash']:
                            raise AppError('IMAGE_INPUT_CHANGED', 'Frozen prompt bytes changed.')
                        if job:
                            prepared_proof(root, job, runtime)
                            if digest(request) != job['requestHash']:
                                raise AppError('IMAGE_PREPARED_IDENTITY', 'Prepared dependencies or request changed.')
                    except AppError as error:
                        run.setdefault('blockers', {})[item['assetId']] = {'code': error.code, 'message': error.message}
                        write_json(runpath, sealed(run))
                        stop_new = True
                        continue
                    if job is None:
                        job = {'operationId': operation or str(uuid.uuid4()), 'projectId': plan['projectId'], 'planId': plan_id,
                               'planHash': plan['planHash'], 'assetId': item['assetId'], 'fingerprint': item['fingerprint'],
                               'requestHash': digest(request), 'input': request, 'status': 'prepared',
                               'submissionProtocol': PREPARED_PROTOCOL, 'preparedAt': now(),
                               'authorizationHash': authorization_hash(run), 'attempt': 1,
                               'timings': {'prepared': time.perf_counter()}}
                        job['inputHash'] = digest({'fingerprint': item['fingerprint'], 'input': request})
                        if item.get('retryOf'):
                            job['retryOf'] = item['retryOf']
                            job['attempt'] = jobs_by_id[item['retryOf']]['attempt'] + 1
                        save_job(root, job)
                        jobs_by_id[job['operationId']] = job
                        checkpoint('image-after-prepared', job)
                    if not quota.update(job, reserve=True):
                        capacity_blocked = True
                        waiting_since = waiting_since if waiting_since is not None else time.monotonic()
                        continue
                    waiting_since = None
                    checkpoint('image-after-admission', job)
                    quota.start_submission(job)
                    tasks[asyncio.create_task(one(item, job, True))] = item
                    pending.remove(item)
                    launched = True
                    await asyncio.sleep(0)
                finished = {task for task in tasks if task.done()}
                for task in finished:
                    task.result()
                    del tasks[task]
                if not tasks:
                    if capacity_blocked and waiting_since is not None and time.monotonic()-waiting_since < capacity_wait:
                        await asyncio.sleep(capacity_poll)
                        continue
                    break
                if not launched:
                    changed.clear()
                    try:
                        await asyncio.wait_for(changed.wait(), .02)
                    except TimeoutError:
                        pass
        try:
            await pump()
        finally:
            # A local cancellation stops dispatch. Give in-flight requests a
            # bounded chance to persist receipts before recording unknowns.
            running = [task for task in tasks if not task.done()]
            if running:
                _, remaining = await asyncio.wait(running, timeout=5)
                for task in remaining:
                    task.cancel()
                await asyncio.gather(*running, return_exceptions=True)
        result = collect_images(root, plan_id)
        if quota.diagnostics and not result['complete']:
            result['quotaDiagnostics'] = quota.diagnostics
        from .reporting import write_reports
        write_reports(root, plan, result)
        result['lanes'] = {name: {'observedPeak': lane.peak, 'aggregateWaitMs': lane.wait_ms}
                           for name, lane in [('decode', decode), ('download', downloads), ('registration', register)]}
        write_json(project_path(root, f'{STATE}/image-runs/{plan_id}-timing.json'), sealed(result['lanes']))
        return result


def collect_images(root: Path, plan_id: str) -> dict:
    plan = load_plan(root, plan_id)
    runpath = project_path(root, f'{STATE}/image-runs/{plan_id}.json')
    run = verify(read_json(runpath)) if runpath.exists() else {'items': {}}
    rows = []
    plans = {plan_id: plan}
    for item in plan['items']:
        operation = run['items'].get(item['assetId']) or item.get('operationId')
        row = {'assetId': item['assetId'], 'status': 'reused' if item['action'] == 'reuse' else 'pending'}
        if item['action'] == 'blocked':
            row.update(status='blocked', error=item['blocker'])
            rows.append(row)
            continue
        job_path = project_path(root, f'{STATE}/image-jobs/{operation}.json') if operation else None
        if job_path is not None and job_path.exists():
            job = load_image_job(root, operation, plans)
            if job['assetId'] != item['assetId'] or job['projectId'] != plan['projectId'] or job['fingerprint'] != item['fingerprint']:
                raise AppError('IMAGE_JOB_IDENTITY', 'Image run binding mismatch.')
            row.update(operationId=operation, status=job['status'])
            if job.get('result'):
                result = job['result']
                if sha256(read_stable(project_path(root, result['path']), plan['profile']['maxImageBytes'])) != result['sha256']:
                    raise AppError('IMAGE_RESULT_CHANGED', 'Saved image result changed.')
                row['result'] = result
            if job.get('error'):
                row['error'] = job['error']
        elif item['action'] == 'recover':
            raise AppError('IMAGE_JOB_MISSING', 'Frozen recovery operation is missing; preserve its plan and receipts.')
        elif item['assetId'] in run.get('blockers', {}):
            row.update(status='blocked', error=run['blockers'][item['assetId']])
        elif item['dependencies']:
            row['status'] = 'waiting_dependency'
        rows.append(row)
    return {'planId': plan_id, 'planHash': plan['planHash'], 'complete': all(r['status'] in ('registered', 'reused') for r in rows), 'items': rows}
