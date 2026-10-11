"""Read existing T2 replay evidence without sending model requests."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'development/r067c_retry2_production_control_20261009'))
import ssh_ops


def main():
    out = ROOT / 'development/d09_prediction_20261009/source'
    out.mkdir(parents=True, exist_ok=True)
    sources = {
        'trace': '/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json',
        'trace_rev': '/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json',
        **{f'{arm}_{kind}': f'/data2/_shared/runs/ft_rounds/E1-R003-{version}/{arm}_{kind}.json'
           for arm, version in [('C', 'v4'), ('D', 'v5')]
           for kind in ['coldfirst', 'warm', 'edit']},
    }
    client = ssh_ops.connect()
    try:
        sftp = client.open_sftp()
        manifest = {}
        for name, remote in sources.items():
            with sftp.open(remote, 'rb') as stream:
                data = stream.read()
            target = out / f'{name}.json'
            if target.exists():
                assert target.read_bytes() == data
            else:
                target.write_bytes(data)
            manifest[name] = {'remote': remote, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
            obj = json.loads(data)
            print(name, list(obj))
            if name != 'trace' and name != 'trace_rev':
                print('meta params', obj.get('meta', {}).get('params', {}))
                for row in obj.get('rounds', []):
                    print({k: row.get(k) for k in ['round', 'message_count', 'edit_applied',
                        'edit_at_idx', 'prompt_tokens', 'cached_tokens', 'recomputed_tokens', 'ttft_any_s']})
            elif name == 'trace':
                print('trace summary', obj.get('meta', {}).get('summary'))
                print('record keys', list(obj['rounds'][0]['record']))
        (out / 'SOURCE_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    finally:
        client.close()


if __name__ == '__main__':
    main()
