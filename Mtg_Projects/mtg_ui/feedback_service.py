"""Local, explicit-consent feedback transport; no repository credentials."""
import base64
import binascii
import json
import os
import platform
import re
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from mtg_core.downloads import atomic_json
from mtg_core.paths import core_data_root
from mtg_core.repair import redact

CATEGORIES = ('Report a Bug', 'Suggest a Feature', 'General Feedback')
MAX_SCREENSHOT = 350_000
LIMITS = dict(title=120, description=12000, steps=8000, behavior=8000,
              contact=250, operation=500, diagnostics=50000, screenshot=466668)
WIRE_KEYS = ('id', 'category', 'metadata', *LIMITS)


def payload_for(report):
    """Keep local lifecycle data off the existing relay wire format."""
    payload = {key: report.get(key, '') for key in WIRE_KEYS}
    for key in ('title', 'description', 'steps', 'behavior', 'operation', 'diagnostics'):
        payload[key] = redact(payload[key])
    return payload


def validate_report(report):
    payload = payload_for(report)
    try:
        if uuid.UUID(payload['id']).version != 4:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('This draft has an invalid reference. Please create a new report.') from None
    metadata = payload['metadata']
    if (not isinstance(metadata, dict) or
            not re.fullmatch(r'\d+\.\d+\.\d+-(alpha|beta)\.\d+', str(metadata.get('version', ''))) or
            any(key not in ('version', 'os', 'architecture', 'python') or not isinstance(value, str) or len(value) > 100
                for key, value in metadata.items())):
        raise ValueError('Application version information is unavailable. Please restart Manaforge.')
    if payload['category'] not in CATEGORIES:
        raise ValueError('Choose a feedback type.')
    for key, limit in LIMITS.items():
        if not isinstance(payload[key], str) or len(payload[key]) > limit:
            raise ValueError(f"{key.capitalize()} is too long (maximum {limit:,} characters).")
    if not payload['title'].strip() or not payload['description'].strip():
        raise ValueError('Please add a title and description.')
    try:
        image = base64.b64decode(payload['screenshot'], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Please remove the screenshot and attach it again.') from None
    if image and (len(image) > MAX_SCREENSHOT or not image.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff'))):
        raise ValueError('Choose a PNG or JPEG smaller than 350 KB.')
    if len(json.dumps(payload).encode('utf-8')) > 600_000:
        raise ValueError('Report is too large. Remove the screenshot or shorten the description.')
    return payload


def collect_diagnostics(version, operation='', detail='', extra=''):
    """Bounded local collection only; never make network calls or load catalogs."""
    from mtg_core.health import report_text
    from mtg_core.repair import recent_operations
    from mtg_core.paths import data_root
    events = [dict(event, detail=str(event.get('detail', ''))[-1000:])
              for event in recent_operations()[-10:] if isinstance(event, dict)]
    parts = ['Context: ' + operation, detail[:10000], extra[:8000],
             report_text([], version=version, events=events)]
    # Installed logs, including previous processes, are beneath the stable data root.
    candidates = []
    for root, pattern in ((core_data_root() / 'logs', 'downloads-*.log*'),
                          (core_data_root() / 'logs', 'crash-*.log'),
                          (data_root() / 'crash_logs', '*.log')):
        try:
            for path in root.glob(pattern):
                try:
                    candidates.append((path.stat().st_mtime, path))
                except OSError:
                    continue
        except OSError:
            continue
    for _, path in sorted(candidates, key=lambda entry: entry[0], reverse=True)[:4]:
        try:
            with path.open('rb') as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 4096))
                parts.append(stream.read(4096).decode('utf-8', errors='replace'))
        except OSError:
            continue
    return redact('\n'.join(parts))[:50000]



def new_report(version, operation='', detail=''):
    return dict(id=str(uuid.uuid4()), category=CATEGORIES[0], title=operation[:120],
                description=redact(detail), steps='', behavior='', contact='', diagnostics='',
                screenshot='', status='draft', metadata=dict(version=version, os=platform.system(),
                architecture=platform.machine(), python=platform.python_version()), operation=redact(operation))


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else core_data_root() / 'feedback'

    def path(self, report_id):
        return self.root / (str(uuid.UUID(report_id)) + '.json')

    def save(self, report):
        atomic_json(self.path(report['id']), report)

    def reports(self):
        for path in sorted(self.root.glob('*.json')):
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
                self.path(value['id'])
                yield value
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def delete(self, report_id):
        self.path(report_id).unlink(missing_ok=True)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def submit(report, endpoint=None, invite=None):
    endpoint = endpoint or os.environ.get('MANAFORGE_FEEDBACK_URL', '')
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Feedback is not configured. Your report is saved; ask the maintainer for setup help.')
    if report.get('status') == 'submitted':
        return dict(id=report['id'], reference=report['reference'])
    invitation = invite or os.environ.get('MANAFORGE_FEEDBACK_INVITE', '')
    if not invitation:
        raise ValueError('The feedback invitation is not configured. Ask the maintainer to set it up, then restart Manaforge.')
    payload = validate_report(report)
    data = json.dumps(payload).encode('utf-8')
    request = Request(endpoint, data=data, headers={'Content-Type': 'application/json',
        'X-Feedback-Invite': invitation}, method='POST')
    try:
        with build_opener(NoRedirect()).open(request, timeout=25) as response:
            result = json.loads(response.read(8192))
    except HTTPError as exc:
        messages = {404: 'The feedback server address is incorrect. Check that it ends in /feedback.',
                    403: 'The feedback invitation is unavailable. Ask the maintainer for help.',
                    409: 'Your report is stored on the server and needs maintainer confirmation. Keep this report.',
                    429: 'Too many reports were sent recently. Please try again in a minute.',
                    503: 'The feedback service could not confirm submission. Please try again later.'}
        raise ValueError(messages.get(exc.code, 'The feedback service could not accept this report. Please try again later.')) from None
    except (URLError, OSError, ValueError):
        raise ValueError("Couldn't connect to the feedback service. Please try again later.") from None
    if not isinstance(result, dict):
        raise ValueError('Submission was not confirmed. Keep this report and retry with the same reference.')
    if result.get('id') != report['id'] or not result.get('reference'):
        raise ValueError('Submission was not confirmed. Keep this report and retry with the same reference.')
    return result
