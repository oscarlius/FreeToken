"""Select the initial or sole preapproved retry service generation."""
import json
from pathlib import Path
import sys


def select(approval, retry=False):
    approval = dict(approval)
    assert approval['conditions_met']
    if retry:
        original = Path(approval['run_dir'])
        result = json.loads((original / 'smoke_execution_result.json').read_text())
        ledger = json.loads((original / 'smoke_campaign.json').read_text())
        assert result['exit_code'] == 75 and result['classification'] == 'smoke_invalid'
        assert (original / 'stopped.json').is_file()
        assert len(ledger['attempts']) == 1 and ledger['attempts'][0]['outcome'] == 'smoke_invalid'
        assert ledger['reference_sha256'] == approval['expected_reference_sha256']
        assert approval['retry_approval'] == approval['approval_id'] + '-retry1'
        approval['approval_id'] = approval['retry_approval']
        approval['run_dir'] = str(original.parent / approval['approval_id'])
    assert Path(approval['campaign_dir']) == Path(approval['run_dir']).parent / (
        approval['approval_id'].removesuffix('-retry1'))
    return approval


def load():
    if sys.argv[1:] not in ([], ['--retry1']):
        raise ValueError('Only the explicit --retry1 option is permitted')
    source = Path(__file__).with_name('DEPLOYMENT_APPROVAL.json')
    return select(json.loads(source.read_text()), bool(sys.argv[1:]))
