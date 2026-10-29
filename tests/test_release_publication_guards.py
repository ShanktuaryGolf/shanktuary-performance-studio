"""Execute the release workflow's actual Python guards with a fake GitHub API.

No release, git or network commands are executed by these tests.
"""

import hashlib
import json
import subprocess
import textwrap
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/build-releases.yml'
SHA = 'a' * 40
TAG = 'v1.8.2'
REPO = 'owner/repository'


def script(marker):
    source = WORKFLOW.read_text().split("python - <<'" + marker + "'\n", 1)[1]
    return textwrap.dedent(source.split('\n          ' + marker, 1)[0])


@pytest.fixture
def release_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for key, value in {'GH_REPO': REPO, 'RELEASE_SHA': SHA, 'RELEASE_TAG': TAG,
                       'RELEASE_ID': '123', 'GITHUB_OUTPUT': str(tmp_path / 'output')}.items():
        monkeypatch.setenv(key, value)
    return tmp_path


def execute(marker, responses, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        assert command[:2] == ['gh', 'api'], 'Only mocked read-only API calls permitted'
        path = command[2]
        calls.append(path)
        assert path in responses, f'Unexpected API request: {path}'
        value = responses[path]
        if value is None:
            return SimpleNamespace(returncode=1, stdout='', stderr='HTTP 404: Not Found')
        return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    exec(compile(script(marker), str(WORKFLOW), 'exec'), {})
    return calls


def preflight_responses():
    return {
        f'repos/{REPO}/git/ref/heads/main': {'object': {'sha': SHA}},
        f'repos/{REPO}/git/ref/tags/{TAG}': None,
        f'repos/{REPO}/releases/tags/{TAG}': None,
    }


def write_versions(path):
    for name in ('obs_server.py', 'shanktuary_performance_studio.py'):
        (path / name).write_text('APP_VERSION = "v1.8.2"\nBUILD_NUMBER = "2026.10.29.1"\n')


def test_preflight_allows_new_release(release_context, monkeypatch):
    write_versions(release_context)
    execute('PYCHECK', preflight_responses(), monkeypatch)
    assert (release_context / 'output').read_text() == 'publish=true\n'


def test_preflight_skips_already_public_release(release_context, monkeypatch):
    write_versions(release_context)
    responses = preflight_responses()
    responses[f'repos/{REPO}/git/ref/tags/{TAG}'] = {'object': {'type': 'commit', 'sha': SHA}}
    responses[f'repos/{REPO}/releases/tags/{TAG}'] = {'draft': False}
    execute('PYCHECK', responses, monkeypatch)
    assert (release_context / 'output').read_text() == 'publish=false\n'


@pytest.mark.parametrize('fault', ['stale_main', 'wrong_tag', 'wrong_version'])
def test_preflight_refuses_unapproved_target(release_context, monkeypatch, fault):
    write_versions(release_context)
    responses = preflight_responses()
    if fault == 'stale_main':
        responses[f'repos/{REPO}/git/ref/heads/main']['object']['sha'] = 'b' * 40
    elif fault == 'wrong_tag':
        responses[f'repos/{REPO}/git/ref/tags/{TAG}'] = {'object': {'type': 'commit', 'sha': 'b' * 40}}
    else:
        (release_context / 'obs_server.py').write_text('APP_VERSION = "v1.8.0"\nBUILD_NUMBER = "2026.10.29.1"\n')
    with pytest.raises(AssertionError):
        execute('PYCHECK', responses, monkeypatch)
    assert not (release_context / 'output').exists()


def upload_responses(path):
    assets = []
    for name in ('Shanktuary-Studio-Linux-x64.tar.gz', 'Shanktuary-Studio-Windows-x64.zip',
                 'Shanktuary-Studio-macOS.zip', 'Shanktuary-Studio-x86_64.AppImage', 'SHA256SUMS.txt'):
        content = ('test-' + name).encode()
        (path / name).write_bytes(content)
        assets.append({'name': name, 'state': 'uploaded', 'size': len(content),
                       'digest': 'sha256:' + hashlib.sha256(content).hexdigest()})
    return {
        f'repos/{REPO}/releases/123': {'draft': True, 'tag_name': TAG, 'target_commitish': SHA},
        f'repos/{REPO}/git/ref/heads/main': {'object': {'sha': SHA}},
        f'repos/{REPO}/git/ref/tags/{TAG}': {'object': {'type': 'commit', 'sha': SHA}},
        f'repos/{REPO}/releases/123/assets': assets,
    }


def test_final_guard_accepts_complete_verified_draft(release_context, monkeypatch):
    execute('PYVERIFY', upload_responses(release_context), monkeypatch)


@pytest.mark.parametrize('fault', ['public_release', 'wrong_tag', 'wrong_target', 'stale_main',
                                  'moved_tag', 'missing_asset', 'extra_asset', 'wrong_size',
                                  'wrong_digest', 'missing_digest', 'unfinished_upload'])
def test_final_guard_refuses_unsafe_publication(release_context, monkeypatch, fault):
    responses = upload_responses(release_context)
    release = responses[f'repos/{REPO}/releases/123']
    assets = responses[f'repos/{REPO}/releases/123/assets']
    if fault == 'public_release':
        release['draft'] = False
    elif fault == 'wrong_tag':
        release['tag_name'] = 'v1.8.0'
    elif fault == 'wrong_target':
        release['target_commitish'] = 'b' * 40
    elif fault == 'stale_main':
        responses[f'repos/{REPO}/git/ref/heads/main']['object']['sha'] = 'b' * 40
    elif fault == 'moved_tag':
        responses[f'repos/{REPO}/git/ref/tags/{TAG}']['object']['sha'] = 'b' * 40
    elif fault == 'missing_asset':
        assets.pop()
    elif fault == 'extra_asset':
        assets.append(dict(deepcopy(assets[0]), name='unexpected.zip'))
    elif fault == 'wrong_size':
        assets[0]['size'] += 1
    elif fault == 'wrong_digest':
        assets[0]['digest'] = 'sha256:' + '0' * 64
    elif fault == 'missing_digest':
        del assets[0]['digest']
    else:
        assets[0]['state'] = 'new'
    with pytest.raises(AssertionError):
        execute('PYVERIFY', responses, monkeypatch)
