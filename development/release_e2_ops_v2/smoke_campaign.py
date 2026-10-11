"""Persist one cold-smoke retry across two explicitly named service generations."""
from contextlib import contextmanager
import json
import os
from pathlib import Path


def save(path, state):
    temporary = path.with_suffix('.pending')
    with temporary.open('x', encoding='utf-8') as handle:
        json.dump(state, handle, indent=2)
        handle.write('\n')
    os.replace(temporary, path)


@contextmanager
def attempt(campaign, production_root, owner, reference_sha256):
    campaign, production_root = Path(campaign), Path(production_root)
    if (campaign.is_symlink() or campaign.resolve() != campaign or
            campaign.parent != production_root or not campaign.is_dir()):
        raise ValueError('Campaign must be the original direct production run directory')
    binding = {'campaign': campaign.name, 'mode': owner['mode'],
               'commit': owner['commit'], 'reference_sha256': reference_sha256}
    path = campaign / 'smoke_campaign.json'
    lock = campaign / 'smoke_campaign.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(str(os.getpid()))
    reserved = False
    state = None
    try:
        state = json.loads(path.read_text()) if path.exists() else {**binding, 'attempts': []}
        if any(state.get(key) != value for key, value in binding.items()):
            raise ValueError('Campaign identity or reference changed')
        ordinal = len(state['attempts'])
        if ordinal and (ordinal != 1 or state['attempts'][0]['outcome'] != 'smoke_invalid'):
            raise RuntimeError('Campaign permits only one retry, after its first smoke_invalid')
        expected = campaign.name + ('-retry1' if ordinal else '')
        if (owner['approval_id'] != expected or
                Path(owner['run_dir']) != production_root / expected):
            raise ValueError('Service generation does not match this campaign attempt')
        state['attempts'].append({'approval_id': expected, 'outcome': 'running'})
        save(path, state)
        reserved = True
        yield state['attempts'][-1]
    finally:
        if reserved:
            if state['attempts'][-1]['outcome'] == 'running':
                state['attempts'][-1]['outcome'] = 'failed'
            save(path, state)
        lock.unlink()
