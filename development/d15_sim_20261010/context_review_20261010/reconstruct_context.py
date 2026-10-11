"""Read-only R046g context audit; count cached prompt tokens, not just prefill work."""
import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

GROUPS = ('G_seed12k', 'G_seed_45k', 'G_seed_real', 'G_two')


def audit(root):
    result = {'definition': 'Per routed decode token: bound full prompt length + prior routed decode tokens of this UID; median over request tokens, in thousands.', 'groups': {}}
    for group in GROUPS:
        directory = root / group
        inputs, bindings, manifest = {}, {}, {}
        for path in sorted(directory.glob('*.binding.json')):
            binding = json.loads(path.read_text())
            uid = int(binding['worker_input']['uid'])
            assert uid not in bindings, (group, uid)
            prompt = int(binding['worker_input']['input_tokens'])
            assert prompt == binding['api']['usage']['prompt_tokens']
            assert prompt == binding['d0']['cached_tokens'] + binding['d0']['new_tokens']
            inputs[uid] = prompt
            bindings[uid] = binding
            manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        d0 = json.loads((directory / 'd0_decode.json').read_text())
        layer_steps = [int(x['steps']) for x in d0['per_layer']['per_layer']]
        full, partial = min(layer_steps), max(layer_steps) > min(layer_steps)
        decoded, prefilled, full_context, calibrated_context = Counter(), Counter(), [], []
        decode_step = 0
        prior_seq = -1
        for path in sorted((directory / 'route').glob('route-*.json')):
            event = json.loads(path.read_text())
            assert event['seq'] > prior_seq
            prior_seq = event['seq']
            for request in event['reqs']:
                uid, count = int(request['rid']), int(request['n_tokens'])
                assert uid in inputs
                if event['phase'] == 'prefill':
                    prefilled[uid] += count
                else:
                    for _ in range(count):
                        context = inputs[uid] + decoded[uid]
                        full_context.append(context)
                        if decode_step < full + int(partial):
                            calibrated_context.append(context)
                        decoded[uid] += 1
            if event['phase'] == 'decode':
                decode_step += 1
        for uid, binding in bindings.items():
            assert prefilled[uid] == binding['route']['accounting']['prefill_tokens']
            assert decoded[uid] == binding['route']['accounting']['route_decode_tokens']
        result['groups'][group] = {
            'full_trace_median_tokens': statistics.median(full_context),
            'full_trace_L_ktok': statistics.median(full_context) / 1000,
            'calibration_prefix_median_tokens': statistics.median(calibrated_context),
            'calibration_prefix_L_ktok': statistics.median(calibrated_context) / 1000,
            'full_trace_decode_steps': decode_step,
            'full_trace_request_tokens': len(full_context),
            'calibration_prefix_request_tokens': len(calibrated_context),
            'uid_accounting': [{'uid': uid, 'prompt_tokens': inputs[uid], 'cached_tokens': bindings[uid]['d0']['cached_tokens'], 'prefill_tokens': prefilled[uid], 'decode_tokens': decoded[uid]} for uid in sorted(inputs)],
            'binding_files_sha256': manifest,
        }
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({group: {key: value for key, value in item.items() if key != 'binding_files_sha256'} for group, item in result['groups'].items()}, indent=2))
