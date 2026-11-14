import asyncio
import copy
import time
from collections import Counter
from types import SimpleNamespace

import pytest

from metasocli_py.contracts.records import validate_record
from metasocli_py.domain.errors import AppError
from metasocli_py.images import workflow as iw
from metasocli_py.images.contracts import ImageJob
from metasocli_py.images.recovery import recover_command
from metasocli_py.persistence.codec import sealed
from metasocli_py.persistence.files import lock, read_json, write_json
from metasocli_py.providers.http import Http
from metasocli_py.providers.yiciyuang import Yiciyuang
from tests.fake_http import FakeProvider
from tests.test_image_http import image_story
from tests.test_process_boundaries import child, wait_until
from tests.test_repair_video import report

PROFILE = {'firstFrameSize': '1920x1088', 'providerLimits': {
    'concurrent': 1, 'source': 'offline synthetic limits', 'checkedAt': '2026-11-13T00:00:00Z'}}


class Crash(BaseException):
    pass


def stop_at(point):
    def checkpoint(actual, job):
        if actual == point:
            raise Crash()
    return checkpoint


async def prepare_job(root, runtime, provider, *, point='image-after-prepared', profile=None):
    plan = iw.plan_images(root, assets=['asset-0'], profile=profile or PROFILE)
    with pytest.raises(Crash):
        await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, confirm=True, checkpoint=stop_at(point))
    return plan, iw.image_jobs(root)[0]


@pytest.mark.parametrize('point', ['image-after-prepared', 'image-after-admission', 'image-after-intent',
                                  'image-post-in-flight', 'image-response-complete'])
def test_real_child_image_protocol_interruptions(tmp_path, monkeypatch, point):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    monkeypatch.setenv('METASOCLI_PY_RUNTIME_DIR', str(tmp_path/'runtime'))
    root = image_story(tmp_path, 1)
    plan = iw.plan_images(root, assets=['asset-0'], profile=PROFILE)
    marker = tmp_path/'checkpoint'
    with FakeProvider() as fake:
        if point == 'image-post-in-flight':
            fake.image_delay = .7
        proc = child(['--origin', fake.origin, '--checkpoint', point, '--marker', marker,
                      'images', 'run', '--root', root, '--plan', plan['planId'], '--confirm'])
        try:
            wait_until(lambda: bool(fake.requests) if point == 'image-post-in-flight' else marker.exists(), proc)
        finally:
            proc.terminate()
            proc.communicate(timeout=10)
        before = len(fake.requests)
        operation = iw.image_jobs(root)[0]['operationId']
        proc = child(['--origin', fake.origin, 'images', 'resume', '--root', root, '--plan', plan['planId']])
        out, err = proc.communicate(timeout=20)
        assert proc.returncode in (0, 2), (out, err)
        unsent = point in ('image-after-prepared', 'image-after-admission')
        assert len(fake.requests) == before + int(unsent)
        job = iw.image_jobs(root)[0]
        assert job['operationId'] == operation
        assert job['status'] == ('registered' if unsent or point == 'image-response-complete' else 'submit_unknown')
        again = child(['--origin', fake.origin, 'images', 'resume', '--root', root, '--plan', plan['planId']])
        out, err = again.communicate(timeout=20)
        assert again.returncode in (0, 2), (out, err)
        assert len(fake.requests) == before + int(unsent)
        report(point, {'postBeforeKill': before, 'resumePosts': int(unsent), 'repeatResumePosts': 0,
                       'finalStatus': job['status'], 'realChildTerminated': True})


def test_two_real_recovery_processes_share_one_prepared_admission(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    monkeypatch.setenv('METASOCLI_PY_RUNTIME_DIR', str(tmp_path/'runtime'))
    root = image_story(tmp_path, 1)
    plan = iw.plan_images(root, assets=['asset-0'], profile=PROFILE)
    marker = tmp_path/'ready'
    with FakeProvider() as fake:
        first = child(['--origin', fake.origin, '--checkpoint', 'image-after-admission', '--marker', marker,
                       'images', 'run', '--root', root, '--plan', plan['planId'], '--confirm'])
        try:
            wait_until(marker.exists, first)
        finally:
            first.terminate()
            first.communicate(timeout=10)
        assert len(fake.requests) == 0
        old = read_json(tmp_path/'runtime/images/yiciyuang-default/ledger.json')['jobs']
        args = ['--origin', fake.origin, 'images', 'resume', '--root', root, '--plan', plan['planId']]
        processes = [child(args), child(args)]
        results = [(proc, proc.communicate(timeout=25)) for proc in processes]
        assert any(proc.returncode == 0 for proc, _ in results), results
        assert all(proc.returncode in (0, 1) for proc, _ in results), results
        for proc, (out, err) in results:
            if proc.returncode:
                assert b'LOCK_BUSY' in out+err
        assert len(fake.requests) == 1
        current = read_json(tmp_path/'runtime/images/yiciyuang-default/ledger.json')['jobs']
        assert list(old) == list(current)
        operation = next(iter(old))
        assert old[operation]['admittedEpoch'] == current[operation]['admittedEpoch']
        proc = child(args)
        out, err = proc.communicate(timeout=20)
        assert proc.returncode == 0 and len(fake.requests) == 1, (out, err)
        report('image-two-processes', {'concurrent': 1, 'resumeProcesses': 2, 'totalPostCount': 1,
            'admissionCount': 1, 'repeatResumePosts': 0, 'ownerCollisionRejected': any(p.returncode for p, _ in results)})


@pytest.mark.asyncio
async def test_live_owner_then_dead_unsent_reservation_frees_other_story(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    runtime = tmp_path/'runtime'
    monkeypatch.setenv('METASOCLI_PY_RUNTIME_DIR', str(runtime))
    a, b = tmp_path/'a', tmp_path/'b'
    a.mkdir()
    b.mkdir()
    root_a, root_b = image_story(a, 1), image_story(b, 1)
    plan_a = iw.plan_images(root_a, assets=['asset-0'], profile=PROFILE)
    plan_b = iw.plan_images(root_b, assets=['asset-0'], profile=PROFILE)
    marker = tmp_path/'ready'
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        first = child(['--origin', fake.origin, '--checkpoint', 'image-after-admission', '--marker', marker,
                       'images', 'run', '--root', root_a, '--plan', plan_a['planId'], '--confirm'])
        try:
            await asyncio.to_thread(wait_until, marker.exists, first)
            blocked = await iw.run_images(root_b, plan_b['planId'], provider=provider, runtime=runtime, confirm=True, capacity_wait=0)
            assert not blocked['complete'] and not fake.requests
        finally:
            first.terminate()
            first.communicate(timeout=10)
        try:
            result = await iw.run_images(root_b, plan_b['planId'], provider=provider, runtime=runtime, resume=True, capacity_wait=0)
            assert result['complete'] and len(fake.requests) == 1
            original = iw.image_jobs(root_a)[0]
            assert original['status'] == 'prepared' and 'sentEpoch' not in original
            slots = iw.Quota(runtime, plan_a['profile'], root_a).read()['jobs']
            slot = slots[original['operationId']]
            assert slot['admissionState'] == 'released'
            assert slot['audit'][-1]['reason'] == 'owner_exited_proven_unsent'
            result = await iw.run_images(root_a, plan_a['planId'], provider=provider, runtime=runtime, resume=True, capacity_wait=0)
            assert result['complete'] and len(fake.requests) == 2
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_prepared_recover_is_zero_post_and_admission_is_idempotent_rpm(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    runtime = tmp_path/'runtime'
    root = image_story(tmp_path, 2)
    profile = {**PROFILE, 'providerLimits': {**PROFILE['providerLimits'], 'concurrent': 2, 'rpm': 1}}
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            plan, job = await prepare_job(root, runtime, provider, profile=profile)
            result = await recover_command(root, SimpleNamespace(operation=job['operationId'], action='recover'), provider, runtime)
            assert result['items'][0]['status'] == 'prepared' and fake.requests == []
            quota = iw.Quota(runtime, plan['profile'], root)
            with lock(root/'.metasocli-py/submission.lock'):
                assert quota.update(job, reserve=True)
                once = copy.deepcopy(quota.read()['jobs'][job['operationId']])
                assert quota.update(job, reserve=True)
                assert quota.read()['jobs'][job['operationId']] == once
            other = iw.plan_images(root, assets=['asset-1'], profile=profile)
            blocked = await iw.run_images(root, other['planId'], provider=provider, runtime=runtime, confirm=True, capacity_wait=0)
            assert not blocked['complete'] and not fake.requests
            # Same operation reuses its prepaid RPM token even when the window is full.
            final = await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, resume=True)
            assert final['complete'] and len(fake.requests) == 1
            blocked = await iw.run_images(root, other['planId'], provider=provider, runtime=runtime, resume=True, capacity_wait=0)
            assert not blocked['complete'] and len(fake.requests) == 1
            clock = iw.time.time()
            monkeypatch.setattr(iw.time, 'time', lambda: clock+61)
            final = await iw.run_images(root, other['planId'], provider=provider, runtime=runtime, resume=True)
            assert final['complete'] and len(fake.requests) == 2
        finally:
            await provider.http.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('evidence', ['legacy-no-job', 'legacy-unknown', 'receipt-conflict', 'request-conflict'])
async def test_unproven_orphans_are_not_released(tmp_path, monkeypatch, evidence):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    runtime = tmp_path/'runtime'
    a, b = tmp_path/'a', tmp_path/'b'
    a.mkdir()
    b.mkdir()
    root, other = image_story(a, 1), image_story(b, 1)
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            plan, job = await prepare_job(root, runtime, provider, point='image-after-admission')
            quota = iw.Quota(runtime, plan['profile'], root)
            data = quota.read()
            slot = data['jobs'][job['operationId']]
            if evidence.startswith('legacy'):
                for key in ('submissionProtocol', 'authorizationHash', 'preparedAt'):
                    job.pop(key, None)
                    slot.pop(key, None)
                job.update(status='submit_unknown', sentEpoch=iw.time.time(), requestStartedAt=iw.now())
                slot.update(status='submit_unknown', sentEpoch=job['sentEpoch'])
                iw.save_job(root, job)
                if evidence == 'legacy-no-job':
                    (root/f'.metasocli-py/image-jobs/{job["operationId"]}.json').unlink()
            elif evidence == 'receipt-conflict':
                write_json(root/f'.metasocli-py/image-receipts/{job["operationId"]}/complete.json', {'broken': True})
            else:
                slot['requestHash'] = '0'*64
            quota.save(data)
            before = quota.read()['jobs'][job['operationId']]
            other_plan = iw.plan_images(other, assets=['asset-0'], profile=PROFILE)
            result = await iw.run_images(other, other_plan['planId'], provider=provider, runtime=runtime, confirm=True, capacity_wait=0)
            assert not result['complete'] and not fake.requests
            assert quota.read()['jobs'][job['operationId']] == before
            assert result['quotaDiagnostics'][0]['code'] == 'IMAGE_QUOTA_HELD'
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_protocol_timestamps_and_changed_prepared_inputs_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = image_story(tmp_path, 1), tmp_path/'runtime'
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            plan, job = await prepare_job(root, runtime, provider)
            for change in ({'sentEpoch': 1.0}, {'requestStartedAt': 'fake'}, {'status': 'submitting'},
                           {'submissionProtocol': None}, {'timings': {'send': 1.0}},
                           {'status': 'submitting', 'sentEpoch': 1.0, 'requestStartedAt': 'invalid-time'}):
                with pytest.raises(AppError):
                    validate_record(ImageJob, sealed({**job, **change}))
            (root/job['input']['promptPath']).write_text('changed synthetic prompt', encoding='utf-8')
            result = await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, resume=True, capacity_wait=0)
            assert not result['complete'] and not fake.requests
            assert iw.image_jobs(root)[0]['status'] == 'prepared'
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_released_prepared_readmission_charges_new_rpm_window(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    runtime = tmp_path/'runtime'
    a, b = tmp_path/'a', tmp_path/'b'
    a.mkdir()
    b.mkdir()
    root, other = image_story(a, 1), image_story(b, 1)
    profile = {**PROFILE, 'providerLimits': {**PROFILE['providerLimits'], 'rpm': 1}}
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            plan, job = await prepare_job(root, runtime, provider, point='image-after-admission', profile=profile)
            other_plan = iw.plan_images(other, assets=['asset-0'], profile=profile)
            result = await iw.run_images(other, other_plan['planId'], provider=provider, runtime=runtime, confirm=True, capacity_wait=0)
            assert not result['complete'] and not fake.requests
            quota = iw.Quota(runtime, plan['profile'], root)
            prior = quota.read()['jobs'][job['operationId']]
            assert prior['admissionState'] == 'released'
            clock = iw.time.time()
            monkeypatch.setattr(iw.time, 'time', lambda: clock+61)
            result = await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, resume=True)
            assert result['complete'] and len(fake.requests) == 1
            slot = quota.read()['jobs'][job['operationId']]
            assert slot['admittedEpoch'] > prior['admittedEpoch']
            result = await iw.run_images(other, other_plan['planId'], provider=provider, runtime=runtime, resume=True, capacity_wait=0)
            assert not result['complete'] and len(fake.requests) == 1
            assert any(d['code'] == 'IMAGE_RPM_LIMIT' for d in result['quotaDiagnostics'])
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_image_protocol_local_write_counts(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = image_story(tmp_path, 1), tmp_path/'runtime'
    plan = iw.plan_images(root, assets=['asset-0'], profile=PROFILE)
    counts = Counter()
    actual = iw.write_json
    def counted(path, value):
        if path.name == 'ledger.json':
            counts['quotaLedger'] += 1
        elif path.parent.name == 'image-jobs':
            counts['job:'+value['status']] += 1
        elif path.name == plan['planId']+'.json' and path.parent.name == 'image-runs':
            counts['authorization'] += 1
        return actual(path, value)
    monkeypatch.setattr(iw, 'write_json', counted)
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            began = time.perf_counter()
            result = await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, confirm=True)
            elapsed = (time.perf_counter()-began)*1000
            assert result['complete'] and len(fake.requests) == 1
            assert counts['job:prepared'] == counts['job:submitting'] == counts['authorization'] == 1
            assert counts['quotaLedger'] == 3
            report('image-writes', {'observedWorkflowJsonWrites': dict(counts), 'elapsedMs': elapsed,
                'postCount': 1, 'protocolChangesPerRequestVsReviewedSource': {
                    'additionalPreparedJobWrite': 1, 'additionalIntentLedgerWrite': 1,
                    'removedRedundantRunBindingWrite': 1, 'netAdditionalWrites': 1},
                'countScope': 'workflow.write_json; response stream and other-module receipt writes excluded'})
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_admission_rechecked_before_post(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = image_story(tmp_path, 1), tmp_path/'runtime'
    plan = iw.plan_images(root, assets=['asset-0'], profile=PROFILE)
    quota = iw.Quota(runtime, plan['profile'], root)
    def revoked(point, job):
        if point == 'image-after-intent':
            data = quota.read()
            data['jobs'][job['operationId']]['admissionState'] = 'released'
            quota.save(data)
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            result = await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, confirm=True, checkpoint=revoked)
            assert not fake.requests and not result['complete']
            assert result['items'][0]['error']['code'] == 'IMAGE_QUOTA_OWNER'
            await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, resume=True)
            assert not fake.requests
        finally:
            await provider.http.close()
