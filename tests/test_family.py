"""The host exposes the canonical copilot without creating check data."""
import importlib

from fastapi.testclient import TestClient


def test_copilot_mount_and_health_do_not_create_checks(tmp_path, monkeypatch):
    monkeypatch.setenv('SHANNON_DATA', str(tmp_path))
    from shannon import app as module
    module = importlib.reload(module)
    with TestClient(module.app) as client:
        assert client.get('/api/health').json()['service'] == 'shannon-hoard'
        home = client.get('/')
        assert home.status_code == 200
        assert home.text.count('src="/api/copilot/launcher.js"') == 1
        assert not (tmp_path / 'records').exists()
        info = client.get('/api/copilot/info')
        assert info.status_code == 200
        assert info.json()['app_id'] == 'shannon'
        launcher = client.get('/api/copilot/launcher.js')
        assert launcher.status_code == 200
        assert 'Faustus' in launcher.text
        assert not (tmp_path / 'records').exists()
