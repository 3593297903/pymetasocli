import threading
from urllib.parse import urlsplit

import httpx
import pytest

from metasocli_py.application.skills import ENTRIES, install, payloads, uninstall
from metasocli_py.credentials.config import credential, save_credential, status
from metasocli_py.credentials.connect import form_server
from metasocli_py.domain.errors import AppError


def test_dpapi_backup_failed_replace_and_status(tmp_path, monkeypatch):
    folder = tmp_path/'config'
    monkeypatch.setenv('METASOCLI_PY_CONFIG_DIR', str(folder))
    save_credential('images', 'synthetic-first-token')
    assert credential('images') == 'synthetic-first-token'
    old = (folder/'images.json').read_bytes()
    assert b'synthetic-first-token' not in old
    save_credential('images', 'synthetic-second-token')
    current = (folder/'images.json').read_bytes()
    assert next((folder/'backups').glob('*.json')).read_bytes() == old
    assert status('images', decrypt=True) == {'provider': 'images', 'configured': True, 'source': 'dpapi',
        'decryptChecked': True, 'remoteAuthentication': 'not-tested', 'generation': 'not-tested'}
    import metasocli_py.credentials.config as config
    monkeypatch.setattr(config, 'crypt', lambda *_args, **_kwargs: (_ for _ in ()).throw(AppError('TEST', 'synthetic failure')))
    with pytest.raises(AppError):
        save_credential('images', 'third')
    assert (folder/'images.json').read_bytes() == current


def test_local_form_host_origin_token_single_use(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    monkeypatch.setenv('METASOCLI_PY_CONFIG_DIR', str(tmp_path/'config'))
    server, url, state = form_server('metaso', ttl=10)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(trust_env=False) as client:
            assert client.get(url).status_code == 200
            assert client.get(url, headers={'Host': 'evil.invalid'}).status_code == 403
            assert client.post(url, data={'key': 'synthetic'}, headers={'Origin': 'http://evil.invalid'}).status_code == 403
            parts = urlsplit(url)
            headers = {'Origin': f'{parts.scheme}://{parts.netloc}'}
            assert client.post(url, data={'key': 'synthetic-only'}, headers=headers).status_code == 200
            assert client.post(url, data={'key': 'changed'}, headers=headers).status_code == 403
        assert state['saved'] and credential('metaso') == 'synthetic-only'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_three_skills_temp_discovery_and_rollback(tmp_path):
    old = tmp_path/'metasocli'
    old.mkdir()
    (old/'SKILL.md').write_bytes(b'old untouched')
    before = (old/'SKILL.md').read_bytes()
    assert len([p for p in payloads() if p.endswith('/SKILL.md')]) == 6
    install(tmp_path)
    assert all((tmp_path/name/'SKILL.md').is_file() for name in ENTRIES)
    assert install(tmp_path)['alreadyInstalled']
    assert all((tmp_path/name/'references/package/metasocli-py-reference-images/SKILL.md').is_file() for name in ENTRIES)
    edited = tmp_path/ENTRIES[0]/'user.txt'
    edited.write_bytes(b'keep user data')
    with pytest.raises(AppError):
        uninstall(tmp_path)
    edited.unlink()
    uninstall(tmp_path)
    assert (old/'SKILL.md').read_bytes() == before
    assert not any((tmp_path/name).exists() for name in ENTRIES)
