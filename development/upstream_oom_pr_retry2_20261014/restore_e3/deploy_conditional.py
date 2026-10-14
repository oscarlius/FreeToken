"""Only explicit start/wait adapters are allowed for this new E3 identity."""
import hashlib, json, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
def require_root_final_review(approval):
    review=json.loads((HERE/'ROOT_FINAL_REVIEW.json').read_text())
    if not approval['conditions_met'] or review.get('verdict')!='PASS':
        raise RuntimeError('PENDING independent recovery review')
    data=(HERE/'DEPLOYMENT_APPROVAL.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=review['approval_sha256'] or json.loads(data)!=approval:
        raise RuntimeError('Recovery approval changed')
    manifest_path=HERE/'SOURCE_MANIFEST.json'
    digest=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if digest!=review['package_source_manifest_sha256'] or digest!=approval['package_source_manifest_sha256']:
        raise RuntimeError('Recovery source manifest changed')
    for name, expected in json.loads(manifest_path.read_text())['files'].items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Recovery source changed: '+name)
    sys.path.insert(0,str(HERE.parent))
    from recovery_guard import verify_sources
    verify_sources(approval)
if __name__=='__main__':
    raise SystemExit('Use only explicit start_approved_release.py and wait_release_and_smoke.py; no old observer or automatic retry')
