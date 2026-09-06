"""Apply docs/repository-metadata.json to the origin GitHub repository.

Uses GITHUB_TOKEN/GH_TOKEN or the configured Git credential helper without
printing credentials. Existing topics are retained. No git commits or pushes.
"""
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    remote = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=ROOT, text=True).strip()
    if remote.startswith('git@github.com:'):
        repository = remote.split(':', 1)[1]
    else:
        parsed = urllib.parse.urlparse(remote)
        if parsed.scheme != 'https' or parsed.hostname != 'github.com':
            raise RuntimeError('Origin must be a GitHub repository.')
        repository = parsed.path.lstrip('/')
    repository = repository.removesuffix('.git')
    if len(repository.split('/')) != 2:
        raise RuntimeError('Invalid GitHub repository path.')
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if not token:
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
        result = subprocess.run(['git', 'credential', 'fill'], cwd=ROOT, env=env,
            input=f'protocol=https\nhost=github.com\npath={repository}.git\n\n',
            text=True, capture_output=True, timeout=30)
        credentials = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        token = credentials.get('password')
    if not token:
        raise RuntimeError('No GitHub credential is available. Metadata is ready in docs/repository-metadata.json.')

    def api(path='', method='GET', payload=None):
        request = urllib.request.Request('https://api.github.com/repos/' + repository + path,
            data=None if payload is None else json.dumps(payload).encode(), method=method,
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json', 'User-Agent': 'mtg-suite-metadata'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    metadata = json.loads((ROOT / 'docs/repository-metadata.json').read_text())
    current = api()
    topics = list(dict.fromkeys(current.get('topics', []) + metadata['topics']))
    if len(topics) > 20:
        raise RuntimeError('Adding these topics would exceed GitHub’s 20-topic limit; existing topics were not changed.')
    if current.get('description') != metadata['description']:
        api(method='PATCH', payload={'description': metadata['description']})
    if set(current.get('topics', [])) != set(topics):
        api('/topics', 'PUT', {'names': topics})
    verified = api()
    if verified.get('description') != metadata['description'] or not set(metadata['topics']) <= set(verified.get('topics', [])):
        raise RuntimeError('GitHub metadata verification did not match the requested values.')
    print(f'Updated and verified description and topics for {repository}.')


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f'GitHub API returned HTTP {error.code}; check repository metadata permissions.')
    except (RuntimeError, subprocess.SubprocessError, urllib.error.URLError) as error:
        raise SystemExit(str(error))
