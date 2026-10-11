"""CPU-only R067b packet. Reuse the R067a controller with reviewed tooling changes."""
import ast
import difflib
import hashlib
import importlib.util
import json
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'r067_d20_short_tail_v1'
OPS = Path('/data2/FreeToken/runs/dev_release/release_e2_ops_v5_20261009_review/source/development/release_e2_ops_v2')
RID = 'E2-R067b'
OLD_RID = 'E2-R067a-d20-short-tail'
RUN = Path('/data2/FreeToken/runs/dev_R067') / RID


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    with Path(path).open('x') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')
    Path(path).chmod(0o444)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_once(source, old, new):
    assert source.count(old) == 1, (old, source.count(old))
    return source.replace(old, new)


def main():
    assert not RUN.exists()
    assert not (Path('/data2/_shared/runs/ft_rounds') / RID).exists()
    validator = load(OPS / 'worktree_checks.py', 'r067b_whitelist')
    manifest_path = OPS / 'binary_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    checks = {mode: validator.validate_worktree(item['path'], item['commit'], manifest, mode)
              for mode, item in manifest['worktrees'].items()}
    old_config = json.loads((OLD / 'R067A_V2_2_FILEDRY_CONFIG.json').read_text())
    config = json.loads(json.dumps(old_config).replace(OLD_RID, RID))
    config.update(rid=RID, schema='ft_r067b_filedry_config/v1', retry_of=OLD_RID,
                  retry_index=2, created_utc=datetime.now(timezone.utc).isoformat())
    config['commands']['materialize_per_service'] = 'Copy reviewed async startup wrapper and unchanged exact-ID/observer artifacts; verify all SHA256 values.'
    spawn = config['cpu_file_dry_proof']['startup_spawn']
    spawn.update(path=str(HERE / 'evidence_cpu_v1/receipt.json'),
                 sha256=sha(HERE / 'evidence_cpu_v1/receipt.json'),
                 startup_sha256=sha(HERE / 'tooling/t17_d14_startup.py'))
    spawn['note'] = 'Linux spawn proves original max7 transport/hooks; separate route unittest proves required four P+T/max128 and two P+1/max2 cases with ignore_eos=True.'
    config['binary_manifest'] = {'path': str(manifest_path), 'sha256': sha(manifest_path)}
    assert len(config['services']) == 10 and len(config['generation_budget_book']) == 14
    assert {entry['tail'] for entry in json.loads(Path(config['input_binding']['path']).read_text())['cases']} == {1, 64}
    sockets = []
    try:
        for service in config['services']:
            for port in (service['port_pair']['api'], service['port_pair']['tcpstore']):
                assert port not in (8095, 8096)
                handle = socket.socket()
                handle.bind(('0.0.0.0', port))
                sockets.append(handle)
            service['argv_sha256'] = hashlib.sha256(json.dumps(service['argv'], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            service['startup_materialization'].update(mode='reviewed async481 tooling copy; product engine unchanged', expected_startup_sha256=spawn['startup_sha256'])
    finally:
        for handle in sockets:
            handle.close()
    put(HERE / 'R067B_CONFIG.json', config)
    old_proof = json.loads((OLD / 'R067A_ROOT_BINDINGS_20261009_v1.json').read_text())
    bindings = {path: digest for path, digest in old_proof['bindings'].items()
                if not path.endswith('.so') and 'R067_EXISTING_BINARY_WIRING' not in path}
    for path, digest in bindings.items():
        assert sha(path) == digest, path
    for path in (manifest_path, OPS / 'worktree_checks.py', HERE / 'prepare_bound_command.py',
                 HERE / 'R067B_CONFIG.json', HERE / 'evidence_cpu_v1/receipt.json',
                 HERE / 'evidence_cpu_v1/startup_spawn.log', HERE / 'evidence_cpu_v1/route_unittest.log'):
        bindings[str(path)] = sha(path)
    for path in (HERE / 'tooling').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            bindings[str(path)] = sha(path)
    for mode, item in manifest['worktrees'].items():
        for extension in item['extensions']:
            path = str(Path(item['path']) / extension['path'])
            assert sha(path) == extension['sha256']
            bindings[path] = sha(path)
    for arm, item in config['worktree_binding'].items():
        assert sha(Path(item['path']) / 'python/freetoken/engine/engine.py') == item['engine_sha256']
    proof = {'schema': 'ft_r067b_fresh_bindings/v1', 'checked_utc': datetime.now(timezone.utc).isoformat(),
             'bindings': bindings, 'worktree_checks': checks, 'config_sha256': sha(HERE / 'R067B_CONFIG.json'),
             'passed': True, 'GPU_started': False, 'ports_probed': 20,
             'product_engine_modified': False, 'production_service_started': False}
    put(HERE / 'R067B_ROOT_BINDINGS.json', proof)
    previous = json.loads((OLD / 'R067A_ROOT_EXECUTION_COMMAND_CONFIG.json').read_text())
    source = previous['child_source'].replace(OLD_RID, RID)
    source = replace_once(source, "FD=BASE/'R067A_V2_2_FILEDRY_CONFIG.json'", "FD=Path('" + str(HERE / 'R067B_CONFIG.json') + "')")
    source = replace_once(source, "ADMIT=BASE/'R067A_ROOT_STARTUP_ADMISSION_20261009_v1.json'", "ADMIT=Path('" + str(HERE / 'R067B_ROOT_STARTUP_ADMISSION.json') + "')")
    source = source.replace('0b50e3f9fe60edd5eaca302dbfb29371e7f5b747b4dfff415d79b0447298ea49', sha(HERE / 'R067B_CONFIG.json'))
    source = source.replace('77e26d55b093d5b1e0bf2b88ffa24ce3a2af4ef825857ed2e0b057c2e8c34da8', '__ADMISSION_SHA256__')
    source = replace_once(source, "owned=d07.load_owned_lifecycle()", "owned=d07.load_owned_lifecycle()\nOPS=Path('" + str(OPS) + "')\nchecks=load(OPS/'worktree_checks.py','r067b_runtime_whitelist')\nmanifest=json.loads((OPS/'binary_manifest.json').read_text())\nassert sha(OPS/'binary_manifest.json')==fd['binary_manifest']['sha256']\ndef check_trees():\n for mode,item in manifest['worktrees'].items():checks.validate_worktree(item['path'],item['commit'],manifest,mode)\ndef wait_idle():\n deadline=time.monotonic()+60\n while True:\n  try:return d07.require_gpu_idle()\n  except RuntimeError:\n   if time.monotonic()>=deadline:raise\n   time.sleep(1)\ncheck_trees()")
    source = replace_once(source, "  bindable([service['port_pair']['api'],service['port_pair']['tcpstore']])", "  check_trees()\n  bindable([service['port_pair']['api'],service['port_pair']['tcpstore']])")
    old_materialize = "  wrapper=t17.freeze_startup_wrapper(arm);shutil.copyfile(tool/'t17_d14_observe.py',arm/'t17_d14_observe.py');(arm/'t17_d14_observe.py').chmod(0o444)"
    new_materialize = "  patch_tool=Path('" + str(HERE / 'tooling') + "')\n  for name in ('t17_d14_startup.py','t17_d14_exact_ids.py','t17_d14_observe.py'):\n   shutil.copyfile(patch_tool/name,arm/name);(arm/name).chmod(0o444)\n  wrapper=arm/'t17_d14_startup.py'"
    source = replace_once(source, old_materialize, new_materialize)
    source = source.replace("  d07.require_gpu_idle();bindable", "  wait_idle();bindable")
    source = source.replace("  d07.require_gpu_idle()\n  if owner", "  wait_idle()\n  if owner")
    ast.parse(source.replace('__ADMISSION_SHA256__', '0' * 64))
    parent = previous['parent_source']
    parent = parent[parent.index('ast.parse(CHILD)'):].replace(OLD_RID, RID)
    parent = replace_once(parent, "FD=BASE/'R067A_V2_2_FILEDRY_CONFIG.json';ADMIT=BASE/'R067A_ROOT_STARTUP_ADMISSION_20261009_v1.json'", "FD=Path('" + str(HERE / 'R067B_CONFIG.json') + "');ADMIT=Path('" + str(HERE / 'R067B_ROOT_STARTUP_ADMISSION.json') + "')")
    parent = parent.replace('0b50e3f9fe60edd5eaca302dbfb29371e7f5b747b4dfff415d79b0447298ea49', sha(HERE / 'R067B_CONFIG.json'))
    parent = parent.replace('77e26d55b093d5b1e0bf2b88ffa24ce3a2af4ef825857ed2e0b057c2e8c34da8', '__ADMISSION_SHA256__')
    packet = {'schema': 'ft_r067b_command_template/v1', 'child_source': source, 'parent_tail': parent,
              'changes': ['new round and immutable config/admission bindings', 'reviewed async startup copy',
                          'shared deployment binary manifest whitelist before lock and each spawn',
                          'bounded 60s GPU memory release wait after owned group stops'],
              'engine_changes': False, 'GPU_started': False}
    put(HERE / 'R067B_COMMAND_TEMPLATE.json', packet)
    diff = ''.join(difflib.unified_diff(previous['child_source'].splitlines(True), source.splitlines(True), fromfile='R067a/controller', tofile='R067b/controller'))
    (HERE / 'R067B_CONTROLLER.diff').write_text(diff)
    print(json.dumps({'config_sha256': sha(HERE / 'R067B_CONFIG.json'), 'proof_sha256': sha(HERE / 'R067B_ROOT_BINDINGS.json'), 'template_sha256': sha(HERE / 'R067B_COMMAND_TEMPLATE.json'), 'worktree_modes': list(checks), 'GPU_started': False}))


if __name__ == '__main__':
    main()
