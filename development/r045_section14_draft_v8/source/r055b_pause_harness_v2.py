"""Draft repair for batch79's two observed harness defects; does not launch."""
import json
import urllib.error
import urllib.request


def pause_request(port, seconds, timeout):
    if type(port) is not int or not 0 < port < 65536 or port == 8095:
        raise ValueError('pause probe requires its owned private port')
    request = urllib.request.Request(
        f'http://127.0.0.1:{port}/dev/pause',
        data=json.dumps({'seconds': seconds, 'timeout': timeout}).encode(),
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout + 2) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code != 504:
            raise
        try:
            document = json.load(error)
        except (ValueError, UnicodeError) as malformed:
            raise RuntimeError('pause HTTP504 has no valid JSON timeout receipt') from malformed
        if (not isinstance(document, dict) or document.get('status') != 'timeout'
                or not isinstance(document.get('request_id'), str) or not document['request_id']
                or 'cancel enqueue' in str(document.get('error', ''))):
            raise RuntimeError('pause HTTP504 lacks an identified cancellation timeout receipt')
        return {**document, 'http_status': 504}


def corrected_observer(owner):
    source = owner.PAUSE_OBSERVER
    old = 'elif name=="InputTokenizedMsg":'
    if source.count(old) != 1:
        raise RuntimeError('batch79 observer source contract differs')
    return source.replace(old, 'elif name=="UserMsg":', 1)


def install(owner):
    """Apply both repairs to a newly loaded owner; admission still controls launch."""
    if getattr(owner, '_pause_harness_v2_installed', False):
        raise RuntimeError('pause harness v2 already installed')
    original = owner._legacy
    owner.PAUSE_OBSERVER = corrected_observer(owner)

    def repaired_legacy():
        legacy = original()
        legacy.pause_request = pause_request
        return legacy

    owner._legacy = repaired_legacy
    owner.SOURCE_DEPENDENCIES = (*owner.SOURCE_DEPENDENCIES, 'r055b_pause_harness_v2.py')
    owner._pause_harness_v2_installed = True
