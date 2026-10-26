"""Local, explicit-consent feedback transport; no repository credentials."""
import json
import os
import platform
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from mtg_core.downloads import atomic_json
from mtg_core.paths import core_data_root
from mtg_core.repair import redact

CATEGORIES = ('Report a Bug', 'Suggest a Feature', 'General Feedback')
MAX_SCREENSHOT = 350_000


def new_report(version, operation='', detail=''):
    return dict(id=str(uuid.uuid4()), category=CATEGORIES[0], title=operation[:120],
                description=redact(detail), steps='', behavior='', contact='', diagnostics='',
                screenshot='', metadata=dict(version=version, os=platform.system(),
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
    payload = dict(report)
    for key in ('title', 'description', 'steps', 'behavior', 'operation', 'diagnostics'):
        payload[key] = redact(payload.get(key, ''))
    data = json.dumps(payload).encode('utf-8')
    if len(data) > 600_000:
        raise ValueError('Report is too large. Remove the screenshot or shorten the description.')
    request = Request(endpoint, data=data, headers={'Content-Type': 'application/json',
        'X-Feedback-Invite': invite or os.environ.get('MANAFORGE_FEEDBACK_INVITE', '')}, method='POST')
    with build_opener(NoRedirect()).open(request, timeout=25) as response:
        result = json.loads(response.read(8192))
    if result.get('id') != report['id'] or not result.get('reference'):
        raise ValueError('Submission was not confirmed. Keep this report and retry with the same reference.')
    return result
