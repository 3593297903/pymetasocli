import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from metasocli_py.domain.errors import AppError
from metasocli_py.persistence.files import is_locked, lock, read_json, recover_transactions, safe_path
from metasocli_py.video.capacity import Capacity
from metasocli_py.video.planning import prepare
from tests.fake_http import FakeProvider
from tests.test_video_http import text_story

WORKER = Path(__file__).with_name('process_worker.py')


def wait_until(predicate, process=None, timeout=12):
    until = time.monotonic() + timeout
    while not predicate():
        if process is not None and process.poll() is not None:
            raise AssertionError(process.communicate())
        if time.monotonic() >= until:
            raise AssertionError('Child checkpoint timeout')
        time.sleep(.02)


def child(args, **kwargs):
    return subprocess.Popen([sys.executable, str(WORKER), *map(str, args)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


def test_real_child_stable_lock_owner_and_crash(tmp_path):
    path, marker = tmp_path / 'stable.lock', tmp_path / 'ready'
    proc = child(['--hold-lock', path, '--marker', marker])
    try:
        wait_until(marker.exists, proc)
        inode = path.stat().st_ino
        assert is_locked(path)
        with pytest.raises(AppError, match='owns'):
            with lock(path, timeout=.03):
                pytest.fail('Second process acquired live lock')
        assert path.stat().st_ino == inode
    finally:
        proc.terminate()
        proc.communicate(timeout=10)
    assert path.stat().st_ino == inode and not is_locked(path)


def test_real_transaction_crash_rolls_forward(tmp_path):
    (tmp_path/'a.txt').write_bytes(b'old-a')
    (tmp_path/'b.txt').write_bytes(b'old-b')
    marker = tmp_path/'ready'
    proc = child(['--transaction', tmp_path, '--checkpoint', 'transaction-mid', '--marker', marker])
    try:
        wait_until(marker.exists, proc)
    finally:
        proc.terminate()
        proc.communicate(timeout=10)
    assert (tmp_path/'a.txt').read_bytes() == b'new-a'
    assert (tmp_path/'b.txt').read_bytes() == b'old-b'
    with lock(tmp_path/'.metasocli-py/story.lock'):
        recover_transactions(tmp_path)
    assert (tmp_path/'b.txt').read_bytes() == b'new-b'
    assert read_json(tmp_path/'.metasocli-py/transaction-pending.json') == {'path': None}


@pytest.mark.parametrize('point', ['image-after-intent', 'image-post-in-flight', 'image-response-complete', 'image-after-register'])
def test_killed_image_recovers_without_post(tmp_path, monkeypatch, point):
    from metasocli_py.images.workflow import image_jobs, plan_images
    from tests.test_image_http import image_story
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    monkeypatch.setenv('METASOCLI_PY_RUNTIME_DIR', str(tmp_path/'runtime'))
    root = image_story(tmp_path, 1)
    plan = plan_images(root, assets=['asset-0'], profile={'firstFrameSize': '1920x1088'})
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
        posts = len(fake.requests)
        resumed = child(['--origin', fake.origin, 'images', 'resume', '--root', root, '--plan', plan['planId']])
        out, err = resumed.communicate(timeout=20)
        assert resumed.returncode in (0, 2), (out, err)
        assert len(fake.requests) == posts
        expected = 'submit_unknown' if point in ('image-after-intent', 'image-post-in-flight') else 'registered'
        assert image_jobs(root)[0]['status'] == expected


@pytest.mark.parametrize('point', ['after-intent', 'post-in-flight', 'after-receipt', 'before-job-save',
                                  'after-capacity-event', 'download-before-rename', 'download-after-rename'])
def test_killed_video_never_reposts(tmp_path, monkeypatch, point):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    runtime = tmp_path/'runtime'
    monkeypatch.setenv('METASOCLI_PY_RUNTIME_DIR', str(runtime))
    root = text_story(tmp_path, 1)
    plan = prepare(root, ['ep-1'])
    marker = tmp_path/'checkpoint'
    with FakeProvider() as fake:
        if point == 'post-in-flight':
            fake.create_delay = .7
        args = ['--origin', fake.origin, '--checkpoint', point, '--marker', marker,
                'video', 'run', '--root', root, '--batch', plan['batchId'], '--confirm']
        proc = child(args)
        try:
            wait_until(lambda: bool(fake.events) if point == 'post-in-flight' else marker.exists(), proc)
            capacity = Capacity(runtime)
            if point in ('after-intent', 'post-in-flight', 'after-receipt', 'before-job-save'):
                capacity.audit()
                assert next(iter(capacity.read()['slots'].values()))['capacity']['state'] == 'held'
        finally:
            proc.terminate()
            proc.communicate(timeout=10)
        posts = len(fake.requests)
        resumed = child(['--origin', fake.origin, 'batch', 'resume', '--root', root, '--batch', plan['batchId']])
        out, err = resumed.communicate(timeout=20)
        assert resumed.returncode in (0, 2), (out, err)
        assert len(fake.requests) == posts
        jobs = list((root/'.metasocli-py/jobs').glob('*.json'))
        job = read_json(jobs[0])
        if point in ('after-intent', 'post-in-flight'):
            assert job['status'] == 'submit_unknown'
        else:
            assert job['status'] == 'downloaded', (job, out, err)


def test_windows_path_boundaries(tmp_path):
    file = tmp_path/'original.txt'
    file.write_text('safe')
    hard = tmp_path/'hard.txt'
    os.link(file, hard)
    with pytest.raises(AppError):
        safe_path(hard)
    hard.unlink()
    for value in [str(file)+':hidden', '//server/share/file', r'\\?\C:\secret', str(tmp_path/'CON.txt')]:
        with pytest.raises(AppError):
            safe_path(value)
    assert safe_path(str(file).upper()) == file
    if os.name == 'nt':
        directory = tmp_path/'inside'
        directory.mkdir()
        junction = tmp_path/'junction'
        process = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(directory)], capture_output=True)
        assert process.returncode == 0, process.stderr
        with pytest.raises(AppError):
            safe_path(junction/'new.txt')
