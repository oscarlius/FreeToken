"""R040h collects warm2 and interleave6, retaining R040g parking4 and cold2."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RID = 'E2-R040h'
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
WT = ROOT / 'wt/e2base1-p1'
CANDIDATE = 'effb9969706922ddad9e59b96377e46469ebe97f'
HISTORICAL_COMMIT = '0aa23431e5b800797543bdecbf35a01045131d7d'
REVIEW_DIR = ROOT / 'runs/dev_D16/R040h_startup_review_v1'
DRY = HERE / 'r040h_d16_remaining_dryrun_v1.py'
PINNED_T20_SOURCE = ROOT / 'runs/dev_D16/r040c_v10_source_capsule_20261007_214022/source_tools'
EXTRA = ('r040h_d16_supplement_prepare_base_v1.py', 'r040h_d16_remaining_prepare_v1.py', 'r040h_d16_remaining_dryrun_v1.py',
         'r040f_d16_process_collection_v2.py', 'r040f_d07_g3g4_prepare_v2.py', 'r040a_private_port_owner_v3.py',
         'r040a_anchor_four_cell_v4.py', 't16_private_port_base_runner.py', 'ft_batch_port_pair_v1.py',
         'R040A_D04_FAILED_CLOSURE_20261007.json',
         'd16_native_process_collection_v6.py', 'd16_native_process_collection_v5.py',
         'multisession_probe.py', 'r040f_round_json_append_v1.py')

# This is the actual import closure reached by create_service_owner() and the
# retained D16 collector.  The equiv_suite files are copied from the pinned D16
# CPU source package when a new capsule is assembled; they are not replaced by
# a summary-only collector or by placeholders in a launch package.
RUNTIME_CAPSULE_FILES = (
    'd16_native_process_collection_v2.py', 'd16_native_process_collection_v6.py',
    'd16_native_process_collection_v5.py', 'multisession_probe.py',
    'r040a_d16_process_collection_v4.py',
    't17_d14_artifacts.py', 't17_d14_gpu.py', 't17_d14_runner.py',
    't17_d14_exact_ids.py', 't17_d14_observe.py', 't17_d14_startup.py', 't17_operator_observe.py',
    't17_operator_startup.py', 't16_full_tail_base_runner.py',
    't17_owned_launch_protocol.py', 'd16_service_workloads.py', 'd16_exact_service_startup.py',
    'equiv_suite/__init__.py', 'equiv_suite/service_capture.py', 'equiv_suite/service_capture_startup.py',
    'equiv_suite/sampler_capture.py', 'equiv_suite/native_workloads.py',
    'cpu_guard/sitecustomize.py',
    *(f'helpers/{name}' for name in ('cold_eq.py', 'probe_ft_cold32k.py',
                                     'ft_probe_ckpt_tax.py', 'serve_args_diff.py')),
    *(f'helpers/raw/{name}' for name in ('cold_eq.py', 'probe_ft_cold32k.py',
                                         'ft_probe_ckpt_tax.py', 'serve_args_diff.py')),
)
CAPTURE_ORIGINS = {
    'equiv_suite/sampler_capture.py': 'r040d_capture_v5/equiv_suite/sampler_capture.py',
    'equiv_suite/service_capture.py': 'r040d_capture_v5/equiv_suite/service_capture.py',
    'equiv_suite/service_capture_startup.py': 'r040d_capture_v5/equiv_suite/service_capture_startup.py',
    'd16_exact_service_startup_v4.py': 'r040d_capture_v5/d16_exact_service_startup_v5.py',
    'd16_native_capture_shutdown_v3.py': 'r040d_capture_v5/d16_native_capture_shutdown_v4.py',
}


def required_capsule_files() -> set[str]:
    """Exact source files that a sealed R040a CPU/dry package must carry."""
    base = base_module()
    return set(EXTRA) | {'R040G_RETAINED_PARTIAL_BINDING_20261008.json'} | set(base.REQUIRED) | set(RUNTIME_CAPSULE_FILES) | {
        'r040a_d16_supplement_prepare.py', 'r040f_d07_g3g4_prepare_v2.py',
        't17_continuation_runner.py', 'd17_frozen_helpers.py',
    }


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


INPUT_MANIFEST_RID = 'E2-R040'
INPUT_MANIFEST_NAME = 'source_tools/realinput_28.json'
INPUT_MANIFEST_SHA256 = '90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0'
RETAINED_R040C_METADATA = {
    'round.json': '06fe2ffcb9a23f7dd9c24337ddbe0a43257b8e91d300e4a7124a87dbe745467d',
    'MANIFEST.sha256': 'c53faaf57fbd57451783f3b13da3041a78a09e49a5a8de1df08cb39cb6335a7f',
    'metadata/slots2_group_review.json': '1fadb98d298f5b8459ba9c8ab8b15a57b57d00725d4822ab309ecb9493c33105',
    'metadata/slots2_group_pin.json': '3c4ea1ae6c89b7746612d9f2b5f5655032d2d2a27d53e17b37a9c0a31c6ebcfd',
}

RETAINED_R040D_METADATA = {
    'round.json': '938c7b755978edae1f13e41de9581687185d4837c3a6d8477c727fff390a29e8',
    'MANIFEST.sha256': '51df92f83e344f36fca265545d117a3b9e2c19f9612afd46a374646b58336603',
    'metadata/slots4_batch0_partial_review.json': '11f5fcbcdc39252b6079df423eb54cec2e76a4ae9e6fea449cc4075e10174c88',
    'metadata/slots4_batch0_partial_pin.json': 'faeefa20f4472d2245dda76d8e0953cfec0f2f844e64148157d4cdc759812e68',
}


def retained_slots4_batch0_binding(protocol):
    """Bind the sealed first batch using metadata; leave raw reads to R."""
    canonical = Path(protocol.require_closed_round('E2-R040d', 'failed_harness'))
    directory = ROUNDS / 'E2-R040d'
    if canonical != directory / 'round.json':
        raise RuntimeError('r040h retained first-batch canonical round differs')
    for name, digest in RETAINED_R040D_METADATA.items():
        path = directory / name
        if (any(parent.is_symlink() for parent in (path, *path.parents))
                or not path.is_file() or path.stat().st_mode & 0o222 or sha(path) != digest):
            raise RuntimeError('r040h retained first-batch metadata differs: ' + name)
    review = json.loads((directory / 'metadata/slots4_batch0_partial_review.json').read_text())
    pin = json.loads((directory / 'metadata/slots4_batch0_partial_pin.json').read_text())
    if (json.loads(canonical.read_text()).get('base', {}).get('commit') != HISTORICAL_COMMIT
            or review.get('rid') != 'E2-R040d' or review.get('admitted') is not False
            or review.get('verdict') != 'complete_case_evidence_preserved_not_group_accepted'
            or pin.get('rid') != 'E2-R040d' or pin.get('immutable') is not True
            or pin.get('review_sha256') != RETAINED_R040D_METADATA['metadata/slots4_batch0_partial_review.json']):
        raise RuntimeError('r040h retained first-batch independent review differs')
    path = HERE / 'R040D_RETAINED_BATCH0_BINDING_20261008.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError('r040h retained first-batch binding file is not sealed')
    value = json.loads(path.read_text())
    digest_body = dict(value)
    declared = digest_body.pop('metadata_sha256', None)
    if declared != hashlib.sha256(json.dumps(digest_body, sort_keys=True, separators=(',', ':')).encode()).hexdigest():
        raise RuntimeError('r040h retained first-batch binding content differs')
    expected = {
        'schema': 'ft_r040d_retained_batch0/v1', 'round': 'E2-R040d',
        'candidate_commit': HISTORICAL_COMMIT, 'case': 'dev_D16_4_batch_0_None',
        'round_sha256': RETAINED_R040D_METADATA['round.json'],
        'manifest_sha256': RETAINED_R040D_METADATA['MANIFEST.sha256'],
        'review_sha256': RETAINED_R040D_METADATA['metadata/slots4_batch0_partial_review.json'],
        'pin_sha256': RETAINED_R040D_METADATA['metadata/slots4_batch0_partial_pin.json'],
        'source_round': str(directory),
        'case_root': str(directory / 'dev_D16/native_slots_4/dev_D16_4_batch_0_None'),
        'accepted_group': False, 'raw_not_copied': True,
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise RuntimeError('r040h retained first-batch identity differs')
    ledger = {}
    for line in (directory / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        ledger[name.removeprefix('./')] = digest
    prefix = 'dev_D16/native_slots_4/dev_D16_4_batch_0_None/'
    files = value.get('case_metadata_files')
    if not isinstance(files, dict) or not files or any(
            not name.startswith(prefix) or ledger.get(name) != digest for name, digest in files.items()):
        raise RuntimeError('r040h retained first-batch input/schedule manifest binding differs')
    return {**value, 'binding_file': str(path), 'binding_file_sha256': sha(path),
            'state': 'complete_case_pending_group_combination'}


def retained_slots2_binding(protocol):
    """Validate the already reviewed group using closed metadata only."""
    canonical = Path(protocol.require_closed_round('E2-R040c', 'failed_harness'))
    if canonical != ROUNDS / 'E2-R040c' / 'round.json':
        raise RuntimeError('r040h retained slots2 canonical round differs')
    directory = canonical.parent
    for name, digest in RETAINED_R040C_METADATA.items():
        path = directory / name
        if (any(parent.is_symlink() for parent in (path, *path.parents))
                or not path.is_file() or path.stat().st_mode & 0o222
                or sha(path) != digest):
            raise RuntimeError('r040h retained slots2 sealed metadata differs: ' + name)
    round_doc = json.loads(canonical.read_text())
    review = json.loads((directory / 'metadata/slots2_group_review.json').read_text())
    pin = json.loads((directory / 'metadata/slots2_group_pin.json').read_text())
    if (round_doc.get('base', {}).get('commit') != HISTORICAL_COMMIT
            or review.get('rid') != 'E2-R040c' or review.get('verdict') != 'PASS'
            or review.get('case_count') != 6 or len(review.get('case_names', [])) != 6
            or review.get('recomputation', {}).get('independent_review_verified') is not True
            or pin.get('rid') != 'E2-R040c' or pin.get('verdict') != 'PASS'
            or pin.get('case_count') != 6
            or pin.get('review_sha256') != RETAINED_R040C_METADATA['metadata/slots2_group_review.json']):
        raise RuntimeError('r040h retained slots2 independent review identity differs')
    return {'source_round': 'E2-R040c', 'group': 'S-batch-slots2', 'case_count': 6,
            'state': 'already_reviewed_PASS', 'candidate_commit': HISTORICAL_COMMIT,
            'historical_commit': HISTORICAL_COMMIT,
            'metadata': {name: {'path': str(directory / name), 'sha256': digest}
                         for name, digest in RETAINED_R040C_METADATA.items()}}


def metadata_input_binding(rounds=ROUNDS):
    """Read the authoritative D16 input digest from closed metadata only.

    The historical seed hash deliberately has no role in this binding: the
    actual input bytes are checked later by the retained base executor.
    """
    manifest = Path(rounds) / INPUT_MANIFEST_RID / 'MANIFEST.sha256'
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_mode & 0o222:
        raise RuntimeError('r040h authoritative input manifest missing or mutable')
    matches = []
    for line in manifest.read_text(encoding='utf-8').splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) == 2 and fields[1].removeprefix('./') == INPUT_MANIFEST_NAME:
            matches.append(fields[0])
    if matches != [INPUT_MANIFEST_SHA256]:
        raise RuntimeError('r040h authoritative input manifest binding differs')
    return {'path': str(Path(rounds) / INPUT_MANIFEST_RID / INPUT_MANIFEST_NAME),
            'sha256': INPUT_MANIFEST_SHA256,
            'manifest': str(manifest), 'manifest_sha256': sha(manifest),
            'seed_45k_historical_only': True}


def d04_binding():
    path = HERE / 'R040A_D04_FAILED_CLOSURE_20261007.json'
    document = json.loads(path.read_text())
    report = document['report']
    return {'path': str(path.resolve()), 'sha256': sha(path),
            'round_sha256': report['round_sha256'], 'manifest_sha256': report['manifest_sha256'],
            'independent_review_sha256': report['independent_review_sha256'],
            'receipt_sha256': document['sha256'], 'completed_anchor_arms': report['completed_anchor_arms']}


def r055_section10_basis(protocol, *, read_json=None, digest=None, history_check=None):
    """Reuse R045 v16's two-layer failed-metadata consumer without a kept gate."""
    read_json = read_json or (lambda path: json.loads(Path(path).read_text()))
    digest = digest or sha
    root = ROUNDS / 'E2-R055a-gate-D06'
    pin = ROOT / 'runs/plan_batches/closed_round_pins/E2-R055a-gate-D06_v2.json'
    checks = {pin: 'e785009fe2adecf1116c94b8416bb99093f6d31f14b98bb8df8a3ff3475bd127',
              root / 'round.json': '0c7467a274b93cfd54cdd7d3e70e4b43da6289f93c9a61519dbb3749d75e15b3',
              root / 'MANIFEST.sha256': 'b38e9da3be0781958916fcc5714c8d750645cc10e1ebf4381fe72f5768064ab0'}
    for path, wanted in checks.items():
        if digest(path) != wanted:
            raise RuntimeError('R055a retained metadata SHA differs')
    partial = read_json(root / 'round.json').get('supplemental_independent_raw_review', {})
    if (read_json(pin).get('verdict') != 'failed_harness'
            or read_json(root / 'round.json').get('verdict') != 'failed_harness'
            or partial.get('partial_cold_verdict') != 'PASS'
            or partial.get('sha256') != '10161a2fe801414c3aa611487ead1d8a64a2e7baf1853d90ad4bca7fa7a08aa4'):
        raise RuntimeError('R055a retained cold verdict differs')
    r055b = Path(protocol.require_closed_round('E2-R055b-gate-D06', 'failed_harness'))
    if (digest(r055b) != '13915b0d4657cf9e4ea1e40c64331c938d653f5b318ae16ebaac6f68b8503a4f'
            or digest(r055b.with_name('MANIFEST.sha256')) != '4961ee160759810533dd5702196d38a7760d4f556e6783e8e1f417e84a23432c'):
        raise RuntimeError('R055b sealed failure metadata differs')
    if history_check is not None:
        history_check(root)
    return {'schema': 'ft_r045_section10_basis/v1', 'r055_gate_ended': True,
            'r055c_authorized': False, 'default_path': {'rid': root.name, 'pin_path': str(pin),
            'pin_sha256': checks[pin], 'round_sha256': checks[root / 'round.json'],
            'manifest_sha256': checks[root / 'MANIFEST.sha256'], 'partial_cold_verdict': 'PASS',
            'cold_arms_replayed': False, 'independent_raw_review_sha256': partial['sha256']},
            'r055b_verdict': 'failed_harness', 'r055b_failed_round': str(r055b),
            'r055b_round_sha256': digest(r055b), 'r055b_manifest_sha256': digest(r055b.with_name('MANIFEST.sha256')),
            'pause_chain_validation': 'R045 D06 G3/G4 actual pause/cancel/resume', 'raw_arms_replayed': False}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def base_module():
    base = load(HERE / 'r040h_d16_supplement_prepare_base_v1.py', 'r040a_retained_prepare')
    base.ROOT, base.WT, base.RUNS = ROOT, WT, ROUNDS
    base.CANDIDATE = base.PARENT = CANDIDATE
    base.RID = RID
    base.SCHEMA = 'ft_r040h_d16_supplement_prepare/v1'
    base.REVIEW_DIR = REVIEW_DIR
    return base


def capsule_source_origins(*, pinned_source: Path = PINNED_T20_SOURCE) -> dict[str, Path]:
    """Map every sealed capsule file to its reviewed byte origin.

    A complete source-review archive can recreate itself from its pinned
    flattened leaves. Development assembly without that manifest retains the
    explicit origin mapping below.
    """
    pinned_source = Path(pinned_source)
    required = required_capsule_files()
    if (HERE / 'MANIFEST.sha256').is_file() and not (HERE / 'MANIFEST.sha256').is_symlink():
        sealed = source_bindings()
        if not all(str(HERE / name) in sealed for name in required):
            raise RuntimeError('R040h sealed source archive omits a required capsule role')
        return {name: HERE / name for name in required}
    leaves = {'R040G_RETAINED_PARTIAL_BINDING_20261008.json',
              'r040h_d16_supplement_prepare_base_v1.py',
              'r040h_d16_remaining_prepare_v1.py', 'r040h_d16_remaining_dryrun_v1.py',
              'r040f_d16_process_collection_v2.py', 'r040f_d07_g3g4_prepare_v2.py', 'd16_native_process_collection_v6.py',
              'd16_native_process_collection_v5.py', 'multisession_probe.py', 'r040f_round_json_append_v1.py'}
    return {name: (HERE / CAPTURE_ORIGINS[name] if name in CAPTURE_ORIGINS
                   else HERE / name if name in leaves else pinned_source / name)
            for name in required}


def prepare_source_capsule(destination: Path, *, pinned_source: Path = PINNED_T20_SOURCE) -> dict:
    """Create the minimal R040a source package without copying raw round data."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RuntimeError('R040a source capsule destination must be a new regular path')
    records = {}
    try:
        for name, origin in sorted(capsule_source_origins(pinned_source=pinned_source).items()):
            if (origin.is_symlink() or not origin.is_file() or origin.stat().st_mode & 0o222):
                raise RuntimeError('R040a capsule source is absent, symlinked, or writable: ' + str(origin))
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
            target.chmod(0o444)
            digest = sha(target)
            if digest != sha(origin):
                raise RuntimeError('R040a capsule copy SHA differs: ' + name)
            records[name] = {'origin': str(origin.resolve()), 'sha256': digest}
        manifest = destination / 'MANIFEST.sha256'
        manifest.write_text(''.join(f"{records[name]['sha256']}  {name}\n" for name in sorted(records)), encoding='utf-8')
        manifest.chmod(0o444)
        for path in sorted((item for item in destination.rglob('*') if item.is_dir()), reverse=True):
            path.chmod(0o555)
        destination.chmod(0o555)
        return {'schema': 'ft_r040h_source_capsule/v1', 'destination': str(destination),
                'manifest': str(manifest), 'manifest_sha256': sha(manifest), 'files': records}
    except BaseException:
        # Do not silently leave a partially writable source package for review.
        if destination.exists():
            for path in sorted(destination.rglob('*'), reverse=True):
                try: path.chmod(0o700 if path.is_dir() else 0o600)
                except OSError: pass
        raise


def source_bindings():
    """Bind this actual source capsule, including its retained helper archive."""
    manifest = HERE / 'MANIFEST.sha256'
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_mode & 0o222:
        raise RuntimeError('R040a source capsule requires its frozen manifest')
    declared = {}
    for line in manifest.read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        name = name.removeprefix('./')
        path = HERE / name
        if (len(digest) != 64 or Path(name).is_absolute() or '..' in Path(name).parts
                or name in declared or any(p.is_symlink() for p in (path, *path.parents))
                or not path.is_file() or path.stat().st_mode & 0o222 or sha(path) != digest):
            raise RuntimeError('R040a source inventory differs: ' + name)
        declared[name] = digest
    required = required_capsule_files()
    if not required <= declared.keys():
        missing = sorted(required - declared.keys())
        raise RuntimeError('R040a source manifest omits actual dependencies: ' + ', '.join(missing))
    result = {str(HERE / name): digest for name, digest in declared.items()}
    result[str(manifest)] = sha(manifest)
    return result


R040E_CLOSED_METADATA = {
    'round.json': '7b34f0f319e78c1032cebaab3bfde930cb5ecbbb210cf8a8c636dc9b2afeb617',
    'MANIFEST.sha256': 'ede21cc9c1c1c5c87eb1bca9c14d23570d35c3619adf45d5eb850d81b4e83e08',
}
R040E_D04_REVIEW = ROOT / 'runs/dev_D16/reviews/E2-R040e_failed_harness_review_v1/review.json'
R040E_D04_REVIEW_SHA256 = '1928ac64c8bee653b0c8e290cc1dcf4bdc91c7b03adb12d552ac1857d25a98c1'
R040E_ENVELOPE = ROOT / 'runs/dev_D16/reviews/E2-R040e_slots4_batch_envelope_report_v1/review.json'
R040E_ENVELOPE_SHA256 = 'd770279fcfbfe913e31b2c7d88c1d437dd3999c67492a591d6047abbb8bbebcd'
R040F_CLOSED_METADATA = {
    'round.json': '93849b4f7ae64162c0b9fd6eeb4c05e9e62e6c6b58d406ef0f58f658e56f8ebc',
    'MANIFEST.sha256': '606ff18cd4e2eec6e8cd3a1a1682bbe2d03ed2608d9af431cc81027742ef01a7',
}
R040F_TERMINAL_REVIEW = ROOT / 'runs/dev_D16/reviews/E2-R040f_batch109_terminal_review_v1.json'
R040F_TERMINAL_REVIEW_SHA256 = '01f98811080cfcd3ad07889d45ad710fddd6c113dbfb3b5d1d0e9da2d14e3bac'


def _sealed_sha(path, digest, label):
    path = Path(path)
    if (path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222 or sha(path) != digest):
        raise RuntimeError('r040h sealed metadata differs: ' + label)
    return path


def retained_r040g_partial_binding(protocol):
    """Bind six completed cases through the immutable D04 closure and manifest."""
    directory = ROUNDS / 'E2-R040g'
    canonical = Path(protocol.require_closed_round('E2-R040g', 'failed_harness'))
    if canonical != directory / 'round.json':
        raise RuntimeError('R040h retained R040g canonical path differs')
    path = HERE / 'R040G_RETAINED_PARTIAL_BINDING_20261008.json'
    _sealed_sha(path, '49125e61807a4f4c0fa869c4fea78f59789489c2af4d7fe915f8fdc53b43954e', 'R040g partial binding')
    value = json.loads(path.read_text())
    for name, key in (('round.json', 'round_sha256'), ('MANIFEST.sha256', 'manifest_sha256'),
                      ('independent_terminal_review.json', 'independent_review_sha256')):
        _sealed_sha(directory / name, value[key], 'R040g ' + name)
    _sealed_sha(value['closure_path'], value['closure_sha256'], 'R040g D04 closure')
    _sealed_sha(value['pin_path'], value['pin_sha256'], 'R040g D04 pin')
    if (value.get('schema') != 'ft_r040g_retained_partial/v1'
            or value.get('rid') != 'E2-R040g' or value.get('candidate_commit') != CANDIDATE
            or value.get('source_round') != str(directory) or value.get('case_count') != 6
            or value.get('accepted_full_D16') is not False or value.get('raw_not_copied') is not True
            or [r['arm'] for r in value['parking']['arms']] != ['control_0', 'control_1', 'restore_0', 'restore_1']
            or [r['arm'] for r in value['cache_cold']['arms']] != ['cold_0', 'cold_1']):
        raise RuntimeError('R040h retained case identity or scope differs')
    ledger = {name.removeprefix('./'): digest for digest, name in
              (line.split(maxsplit=1) for line in (directory / 'MANIFEST.sha256').read_text().splitlines())}
    if any(ledger.get(name) != digest for name, digest in value['source_metadata_files'].items()):
        raise RuntimeError('R040h retained summary differs from closed raw manifest')
    return {**value, 'binding_file': str(path), 'binding_file_sha256': sha(path)}


def retained_r040e_slots4_binding(protocol):
    canonical = Path(protocol.require_closed_round('E2-R040e', 'failed_harness'))
    directory = ROUNDS / 'E2-R040e'
    if canonical != directory / 'round.json':
        raise RuntimeError('r040h closed R040e canonical round differs')
    for name, digest in R040E_CLOSED_METADATA.items():
        _sealed_sha(directory / name, digest, name)
    review = _sealed_sha(R040E_D04_REVIEW, R040E_D04_REVIEW_SHA256, 'R040e D04 review')
    envelope = _sealed_sha(R040E_ENVELOPE, R040E_ENVELOPE_SHA256, 'R040e slots4 envelope')
    closed = json.loads(canonical.read_text())
    envelope_doc = json.loads(envelope.read_text())
    if (closed.get('base', {}).get('commit') != HISTORICAL_COMMIT
            or closed.get('verdict') != 'failed_harness'
            or closed.get('independent_review_sha256') != R040E_D04_REVIEW_SHA256
            or envelope_doc.get('schema') != 'ft_r040e_slots4_batch_envelope_report/v1'
            or envelope_doc.get('rid') != 'E2-R040e'
            or envelope_doc.get('result', {}).get('generation_tokens_per_case') != 128
            or envelope_doc.get('result', {}).get('first_divergence_generation_index') is not None):
        raise RuntimeError('r040h retained R040e slots4 evidence identity differs')
    return {'source_round': 'E2-R040e', 'state': 'sealed_completed_slots4_not_rerun',
            'round_sha256': R040E_CLOSED_METADATA['round.json'],
            'manifest_sha256': R040E_CLOSED_METADATA['MANIFEST.sha256'],
            'd04_review': {'path': str(review), 'sha256': R040E_D04_REVIEW_SHA256},
            'batch_envelope': {'path': str(envelope), 'sha256': R040E_ENVELOPE_SHA256},
            'scope_count': 9, 'candidate_commit': HISTORICAL_COMMIT,
            'historical_commit': HISTORICAL_COMMIT,
            'not_candidate_commit': CANDIDATE, 'raw_not_copied': True}


def predecessor_checks(base, after):
    if after != 'E2-R040g':
        raise RuntimeError('r040h requires the closed R040g failed-harness metadata')
    protocol = base.shared_protocol()
    canonical = Path(protocol.require_closed_round('E2-R040f', 'failed_harness'))
    if canonical != ROUNDS / 'E2-R040f' / 'round.json':
        raise RuntimeError('r040h closed R040f canonical round differs')
    for name, digest in R040F_CLOSED_METADATA.items():
        _sealed_sha(canonical.parent / name, digest, 'R040f ' + name)
    review = _sealed_sha(R040F_TERMINAL_REVIEW, R040F_TERMINAL_REVIEW_SHA256,
                         'R040f terminal review')
    if json.loads(review.read_text()).get('rid') != 'E2-R040f':
        raise RuntimeError('r040h R040f terminal review identity differs')
    retained_r040e_slots4_binding(protocol)
    retained_r040g_partial_binding(protocol)
    r055_section10_basis(protocol)
    protocol.checked_worktree(WT)

def create_service_owner(batch, directory, protocol, *, file_dry_run=False):
    base = base_module()
    old = base.load_source(HERE / 't17_continuation_runner.py', 'r040a_native_runtime')
    gpu, _ = base.configure_candidate_runtime(old, {
        'worktree': str(WT), 'candidate_commit': CANDIDATE, 'parent_commit': CANDIDATE})
    helpers = base.load_source(HERE / 'd17_frozen_helpers.py', 'r040a_bound_helpers')
    helpers.bind_protocol(gpu.protocol, HERE / 'helpers')
    lifecycle = protocol.load_owned_lifecycle()
    native = next(cls for cls in gpu.Run.__mro__
                  if cls.__module__ == gpu.__name__ and cls.__name__ == 'Run')

    class SupplementOwner(native):
        def set_status(self, **values):
            if file_dry_run:
                raise RuntimeError('file dry-run cannot publish formal status')
            return gpu.protocol['Runner'].set_status(self, rid=RID, card='T20', **values)

        def environment(self, wt, arm=None, d0=False):
            env = gpu.protocol['Runner'].environment(self, wt, arm, d0)
            for key in list(env):
                if key.startswith('FT_'):
                    env.pop(key)
            if file_dry_run:
                env['CUDA_VISIBLE_DEVICES'] = ''
                env['PYTHONPATH'] = str(HERE / 'cpu_guard') + ':' + env['PYTHONPATH']
            return env

    private = load(HERE / 'r040a_private_port_owner_v3.py', 'r040a_private_owner')
    owner = private.make_owner(gpu, SupplementOwner, lifecycle,
        SimpleNamespace(rid=RID, batch=batch, run=True, gate='T20'),
        directory=directory, file_dry_run=file_dry_run)
    owner.worktree = WT
    owner.status = Path(directory) / f'status_batch{batch}.json'
    owner.token = None if file_dry_run else protocol.LOCK.read_text()
    owner.lock_inode = None if file_dry_run else protocol.LOCK.stat().st_ino
    return owner


def require_dry_run_receipt(path, after):
    path = Path(path)
    if (any(parent.is_symlink() for parent in (path, *path.parents))
            or not path.is_file() or path.stat().st_mode & 0o222
            or path.parent.parent != ROUNDS or path.resolve().parent.parent != ROUNDS.resolve()
            or path.name != 'dry_run_receipt.json'
            or not path.parent.name.startswith('.dryrun_r040h_')):
        raise RuntimeError('r040h requires a sealed receipt in its actual dry sibling')
    document = json.loads(path.read_text())
    expected = {'schema': 'ft_r040h_dry_run/v1', 'rid': RID, 'passed': True,
                'candidate_commit': CANDIDATE, 'worktree': str(WT),
                'script': str(Path(__file__).resolve()), 'formal_entry': str(Path(__file__).resolve()),
                'dry_runner': str(DRY), 'uid': os.getuid(), 'user': getpass.getuser(),
                'cwd': os.getcwd(), 'formal_round_path': str(ROUNDS / RID),
                'receipt_path': str(path.resolve()), 'after_round': after,
                'sources': source_bindings()}
    if any(document.get(key) != value for key, value in expected.items()):
        raise RuntimeError('r040h actual dry receipt identity/source/path differs')
    if document.get('input_binding') != metadata_input_binding(ROUNDS):
        raise RuntimeError('r040h dry receipt input metadata binding differs')
    if document.get('retained_r040e_slots4') != retained_r040e_slots4_binding(base_module().shared_protocol()):
        raise RuntimeError('r040h dry receipt retained slots4 metadata differs')
    if document.get('retained_r040g_partial') != retained_r040g_partial_binding(base_module().shared_protocol()):
        raise RuntimeError('R040h dry receipt retained R040g partial binding differs')
    if document.get('maximum_generation_calls') != 10:
        raise RuntimeError('R040h dry receipt generation-call scope differs')
    if document.get('r055_section10_basis') != r055_section10_basis(base_module().shared_protocol()):
        raise RuntimeError('r040h dry receipt R055 Section 10 basis differs')
    if (type(document.get('port')) is not int or not 1024 <= document['port'] <= 65535
            or document['port'] == 8095 or document.get('service_file_scopes') != 8):
        raise RuntimeError('r040h actual dry receipt port or arm coverage differs')
    if any(document.get(key) is not False for key in (
            'service_started', 'requests_sent', 'gpu_lock_taken', 'batch_allocated',
            'formal_rid_directory_created')):
        raise RuntimeError('r040h dry receipt records prohibited side effects')
    if document.get('foreign_lock_after') not in ('unchanged_absent', 'preserved', 'foreign_owner_finished'):
        raise RuntimeError('R040a foreign lock proof requires a new dry review')
    return {'path': str(path), 'sha256': sha(path), 'document': document}


def child_argv(base, batch, receipt, after, dry_receipt):
    return [str(ROOT / 'venv/bin/python'), str(Path(__file__).resolve()), '--run',
            '--owned-child', '--batch', str(batch), '--launch-receipt', str(receipt),
            '--after-round', after, '--dry-receipt', str(dry_receipt)]


def require_startup_review(base, dry, after):
    """Bind the r040h R decision to closed metadata and the exact current dry run."""
    predecessor_checks(base, after)
    review, pin = REVIEW_DIR / 'review.json', REVIEW_DIR / 'pin.json'
    for path in (REVIEW_DIR, review, pin):
        if path.is_symlink() or not path.exists() or path.stat().st_mode & 0o222:
            raise RuntimeError('r040h sealed startup review/pin required')
    document, binding = json.loads(review.read_text()), json.loads(pin.read_text())
    expected = {'rid': RID, 'verdict': 'PASS', 'candidate_commit': CANDIDATE,
                'after_round': after, 'source_execution_ready': True,
                'model_admitted': False, 'sources': source_bindings(),
                'dry_run_receipt': dry['path'], 'dry_run_receipt_sha256': dry['sha256'],
                'collector_review': dry['document']['collector_review'],
                'collector_review_sha256': dry['document']['collector_review_sha256'],
                'retained_r040e_slots4': retained_r040e_slots4_binding(base.shared_protocol()),
                'retained_r040g_partial': retained_r040g_partial_binding(base.shared_protocol()),
                'r055_section10_basis': r055_section10_basis(base.shared_protocol())}
    if (any(document.get(key) != value for key, value in expected.items())
            or binding.get('rid') != RID or binding.get('review_sha256') != sha(review)
            or binding.get('dry_run_receipt_sha256') != dry['sha256']):
        raise RuntimeError('r040h current review/source/dry-run binding differs')
    anchor = document.get('anchor_four_cell', {})
    if (anchor.get('state') != 'already_complete_in_R040'
            or anchor.get('source_round') != 'E2-R040a'
            or anchor.get('completed_anchor_arms') != 6
            or anchor.get('closed_r040a') != d04_binding()):
        raise RuntimeError('r040h must retain exactly six closed R040a anchors')
    expected_input = metadata_input_binding(ROUNDS)
    inputs = document.get('input_binding', {})
    if any(inputs.get(key) != expected_input[key]
           for key in ('path', 'sha256', 'manifest', 'manifest_sha256')):
        raise RuntimeError('r040h authoritative D16 input metadata binding differs')
    return document


def execute(*, dry_receipt, owned_child=False, batch=None, receipt=None,
            after='E2-R040g'):
    if after != 'E2-R040g':
        raise RuntimeError('r040h requires closed R040g metadata before execution')
    dry = require_dry_run_receipt(dry_receipt, after)
    base = base_module()
    base.require_review = lambda previous: require_startup_review(base, dry, previous)
    base.child_argv = lambda number, launch, previous: child_argv(base, number, launch, previous, dry_receipt)
    base.create_service_owner = create_service_owner
    collector = load(HERE / 'r040f_d16_process_collection_v2.py', 'r040h_private_collection')
    original_body = base.run_supplement_body
    def run_body(*args, **kwargs):
        write_json = kwargs.pop('write_json', None)
        result, provenance = original_body(*args, native_module=collector, **kwargs)
        result.update(rid=RID, schema='ft_r040h_d16_supplement_result/v1',
                      retained_r040e_slots4=retained_r040e_slots4_binding(base.shared_protocol()))
        if (set(result['d16']) != {'cache', 'interleave'}
                or len(result['d16']['cache']['arms']) != 2
                or len(result['d16']['interleave']['arms']) != 6):
            raise RuntimeError('R040h measured collection scope differs from warm2 plus interleave6')
        retained = retained_r040g_partial_binding(base.shared_protocol())
        result['new_services'] = 8
        result['new_generation_calls'] = 10
        result['retained_r040g_partial'] = retained
        result['d16']['parking'] = retained['parking']
        cold = retained['cache_cold']['arms']
        warm = result['d16']['cache']['arms']
        if len(cold) != 2 or [row['arm'] for row in warm] != ['warm_0', 'warm_1']:
            raise RuntimeError('R040h retained cold or new warm arm identity differs')
        all_cache = cold + warm
        if any((row['input_ids_sha256'], row['tokens'], row['text'], row['states']) !=
               (cold[0]['input_ids_sha256'], cold[0]['tokens'], cold[0]['text'], cold[0]['states'])
               for row in all_cache[1:]):
            raise RuntimeError('R040h warm continuation or state differs from retained cold controls')
        result['d16']['cache']['arms'] = all_cache
        result['d16']['cache']['retained_arms'] = ['cold_0', 'cold_1']
        if write_json is not None:
            write_json('d16_input_provenance.json', provenance)
            write_json('r040h_d16_supplement.json', result)
        return result, provenance

    base.run_supplement_body = run_body
    original_load = base.load_source
    base.load_source = lambda path, name: original_load(
        HERE / 'r040a_anchor_four_cell_v4.py' if Path(path).name == 'r040a_anchor_four_cell_v1.py' else path, name)
    original_write = base.write_new

    def write(path, value):
        path = Path(path)
        if path.name in ('r040a_d16_supplement.json', 'r040h_d16_supplement.json', 'result.json'):
            path = path.with_name('r040h_d16_supplement.json') if path.name.startswith('r040a_') else path
            value = {**value, 'rid': RID, 'schema': 'ft_r040h_d16_supplement_result/v1',
                     'retained_r040e_slots4': retained_r040e_slots4_binding(base.shared_protocol())}
        original_write(path, value)
        if Path(path).name == 'admission.json':
            launch = json.loads(Path(receipt).read_text())
            wrapper = Path(launch['wrapper'])
            raw = wrapper.read_bytes()
            if wrapper.is_symlink() or hashlib.sha256(raw).hexdigest() != launch['wrapper_sha256']:
                raise RuntimeError('R040a actual batch wrapper binding differs')
            with (Path(path).parent / 'batch.sh').open('xb') as stream:
                stream.write(raw)

    base.write_new = write
    return base.execute(owned_child=owned_child, batch=batch, receipt=receipt, after=after)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--owned-child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--batch', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--launch-receipt', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--after-round', default='E2-R040g')
    parser.add_argument('--dry-receipt', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--dry-run-dir', type=Path)
    parser.add_argument('--collector-review', type=Path)
    parser.add_argument('--collector-review-sha256')
    parser.add_argument('--anchor-seed-sha256')
    args = parser.parse_args(argv)
    if args.run == args.dry_run:
        parser.error('choose exactly one of --dry-run or --run')
    if args.dry_run:
        if not all((args.dry_run_dir, args.collector_review,
                    args.collector_review_sha256, args.anchor_seed_sha256)):
            parser.error('dry-run requires directory, collector review/SHA and bound seed SHA')
        dry = load(DRY, 'r040h_actual_file_dry')
        return dry.dry_run(args.dry_run_dir, entry=load(Path(__file__), 'r040h_dry_entry'),
                          after=args.after_round, collector_review=args.collector_review,
                          collector_review_sha256=args.collector_review_sha256,
                          seed_sha256=args.anchor_seed_sha256)
    if args.dry_receipt is None:
        parser.error('--run requires --dry-receipt')
    return execute(dry_receipt=args.dry_receipt, owned_child=args.owned_child,
                   batch=args.batch, receipt=args.launch_receipt, after=args.after_round)


if __name__ == '__main__':
    main()

