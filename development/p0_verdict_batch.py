#!/usr/bin/env python3
"""Preflight a pinned P0 review batch, then append through the public D04 writer."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

WRITER_SHA = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
HYPOTHESIS = {'E2-R006', 'E2-R017', 'E2-R011'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_writer(path):
    if sha(path) != WRITER_SHA:
        raise ValueError('D04 writer source differs from reviewed source')
    spec = importlib.util.spec_from_file_location('p0_public_d04', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def planned_document(writer, old, item):
    rid = item['round_id']
    sub = old.get('sub_conclusions', [])
    if not isinstance(sub, list):
        raise ValueError('sub_conclusions must be a list when present')
    updates = item.get('sub_conclusion_status_updates', {})
    identifiers = ', '.join(updates)
    reason = item['rationale'] + ' Scope: measurement validity only.'
    if identifiers:
        reason += ' Reviewed sub_conclusions: ' + identifiers + '.'
    new = writer.run_verdict(old, SimpleNamespace(new=item['proposed_new_verdict'],
        reason=reason, evidence=item['evidence_paths'],
        by='Codex mainline owner under CODEX_HANDOFF_20261004 §2 authorization'))
    new.setdefault('sub_conclusions', [])
    for identifier, status in updates.items():
        matches = [entry for entry in new['sub_conclusions'] if entry.get('id') == identifier]
        if len(matches) != 1 or matches[0].get('status') == 'retracted':
            raise ValueError('explicit status update must name one active existing sub_conclusion')
        matches[0]['status'] = status
    new['sub_conclusions'].append({'id':'P0_measurement_validity',
        'text':'Retained artifacts support the recorded measurements under their actual protocol.',
        'status':'kept','evidence':item['evidence_paths']})
    if rid in HYPOTHESIS:
        new['sub_conclusions'].append({'id':'P0_scientific_attribution',
            'text':'Prefix-hit versus recomputation or restore attribution remains unresolved.',
            'status':'hypothesis','evidence':item['evidence_paths']})
    if rid == 'E2-R008':
        new['sub_conclusions'].append({'id':'P0_snapshot_coverage',
            'text':'Zero successful snapshots in both arms does not establish retained snapshot capability.',
            'status':'hypothesis','evidence':item['evidence_paths']})
    if rid in {'E2-R009', 'E2-R009-p64k'}:
        new['sub_conclusions'].append({'id':'P0_quality_alignment',
            'text':'Historical quality scores require the same judge before cross-round comparison.',
            'status':'hypothesis','evidence':item['evidence_paths']})
    writer.validate_change(old, new)
    return new


def preflight(writer, root, item):
    directory, round_path, history = writer.guarded_round(root / item['round_id'])
    pins = item['canonical_preconditions']
    if sha(round_path) != pins['round_json_sha256']:
        raise ValueError(item['round_id'] + ': current round SHA changed')
    manifest = directory / 'MANIFEST.sha256'
    writer.no_symlink(manifest, '$.MANIFEST.sha256', directory=False)
    if sha(manifest) != pins['manifest_sha256']:
        raise ValueError(item['round_id'] + ': manifest SHA changed')
    old_raw, old, snapshots = writer.validate_history(round_path, history)
    if not snapshots or old.get('round_id') != item['round_id'] or old.get('verdict') != 'pending_review':
        raise ValueError(item['round_id'] + ': unsealed or already judged round')
    if any(path.stat().st_mode & 0o222 for path in [directory, round_path, history, manifest, *snapshots]):
        raise ValueError(item['round_id'] + ': expected readonly sealed state')
    entries = {}
    for line in manifest.read_text().splitlines():
        digest, relative = line.split('  ', 1)
        entries[relative.removeprefix('./')] = digest
    for name in item['evidence_paths']:
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('evidence must be inside the sealed round')
        path = directory / relative
        writer.no_symlink(path, '$.evidence.' + name, directory=False)
        if sha(path) != entries.get(name):
            raise ValueError(item['round_id'] + ': evidence absent from or differs from manifest: ' + name)
    new = planned_document(writer, old, item)
    return {'directory':directory, 'old':old, 'old_raw':old_raw, 'new':new,
        'snapshots':{p.name:p.read_bytes() for p in snapshots}, 'manifest_raw':manifest.read_bytes()}


def receipt_write(path, payload):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    os.replace(temporary, path)


def execute(writer, root, proposal, receipt, apply=False):
    if receipt.exists() or receipt.with_suffix(receipt.suffix + '.tmp').exists():
        raise ValueError('receipt already exists; inspect it before any recovery')
    items = [*proposal['kept_measurements'], proposal['separate_r020_d06']]
    if len({x['round_id'] for x in items}) != len(items):
        raise ValueError('duplicate round in batch')
    plans = [preflight(writer, root, item) for item in items]
    record = {'schema':'ft_p0_verdict_batch/v1','gpu_started':False,
        'applied':apply,'writer_sha256':WRITER_SHA,'all_rounds_preflighted':len(plans),'rounds':[]}
    for item, plan in zip(items, plans):
        record['rounds'].append({'round_id':item['round_id'],'state':'planned',
            'old_round_json_sha256':item['canonical_preconditions']['round_json_sha256'],
            'planned_new_round_json_sha256':hashlib.sha256(writer.json_bytes(plan['new'])).hexdigest(),
            'new_round_json_sha256':None,'manifest_sha256':item['canonical_preconditions']['manifest_sha256'],
            'verdict':plan['new']['verdict'],'history_count':len(plan['snapshots'])+1,
            'sub_conclusions':plan['new']['sub_conclusions']})
    if apply:
        receipt_write(receipt, record)
    for index, (item, plan) in enumerate(zip(items, plans)):
        directory = plan['directory']
        if apply:
            if (directory/'round.json').read_bytes() != plan['old_raw']:
                raise ValueError('round changed since complete batch preflight')
            record['rounds'][index]['state'] = 'committing'
            receipt_write(receipt, record)
            writer.commit(directory, plan['new'])
            _, actual, snapshots = writer.validate_history(directory/'round.json', directory/'round_history')
            if not writer.exact_equal(actual, plan['new']):
                raise ValueError('committed document differs from planned transition')
            for name, raw in plan['snapshots'].items():
                if (directory/'round_history'/name).read_bytes() != raw:
                    raise ValueError('historical snapshot changed')
            if (directory/'MANIFEST.sha256').read_bytes() != plan['manifest_raw']:
                raise ValueError('raw artifact manifest changed')
            new_sha, history_count = sha(directory/'round.json'), len(snapshots)
        else:
            new_sha, history_count = None, len(plan['snapshots']) + 1
        record['rounds'][index].update(state='committed' if apply else 'planned',
            new_round_json_sha256=new_sha,history_count=history_count)
        if apply:
            receipt_write(receipt, record)
    if not apply:
        receipt_write(receipt, record)
    receipt.chmod(receipt.stat().st_mode & ~0o222)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposal', type=Path, required=True)
    parser.add_argument('--writer', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    proposal = json.loads(args.proposal.read_text(encoding='utf-8'))
    record = execute(load_writer(args.writer), args.root, proposal, args.receipt, args.apply)
    print(json.dumps({'applied':record['applied'],'rounds':len(record['rounds']),
        'receipt_sha256':sha(args.receipt)}))


if __name__ == '__main__':
    main()
