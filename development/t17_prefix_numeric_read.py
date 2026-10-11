"""CPU-only independent read of exact R027, using the retained review program."""
import argparse
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess

RID = 'E2-R027-diagnostic-T17'
BATCH = 55
COMPANION_SHA = '4a682715d648b811c0157eb670e2a5e9b8b261124241f0f8dc40136d7b8e0685'
PROGRAM_SHA = '94994363b871e220849a15d41eaaf4639ba418a6ce1e40c88176d25c6dcbc116'
CPU_SHA = '85cf811e1d0d91c8c6e6e0dbd826edfc80a9793f7061b3cb7e4f653a8148ec7c'
NUMERIC = tuple('prefix_1_%04d_%s.pt' % (i, name) for i, name in enumerate(
    ('conv_in','q','k','v','g','beta','conv_in','q','k','v','g','beta','h_8192'), 1))
DUMP_FIELDS = ('dev_conv_states','dev_ple_conv','dev_ple_ngram_ctx','dev_recurrent_states')
EXPECTED_TENSORS = ({'numeric_cold/numeric/'+name for name in NUMERIC}
                    | {'numeric_warm/numeric/'+name for name in NUMERIC}
                    | {'numeric_cold/dump/donate_0001_'+name+'.pt' for name in DUMP_FIELDS}
                    | {'numeric_warm/dump/'+prefix+'_'+name+'.pt'
                       for prefix in ('donate_0001','donate_0003','resume-device_0002')
                       for name in DUMP_FIELDS})

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def companion_program():
    path = Path(__file__).with_name('t17_r027_independent_cpu_review.py')
    if path.is_symlink() or sha256(path) != COMPANION_SHA:
        raise ValueError('retained independent CPU source changed')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    values = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == 'PROGRAM' for t in node.targets)]
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError('one retained CPU PROGRAM required')
    return values[0]

def require_inventory(names):
    if set(names) != EXPECTED_TENSORS:
        raise ValueError('complete exact 42-tensor inventory required')

def read_actual(receipt, program=None, reader_sha=None):
    """Run on host9; no remote writes, GPU work or lifecycle changes."""
    program = companion_program() if program is None else program
    if not isinstance(program, str) or hashlib.sha256(program.encode()).hexdigest() != PROGRAM_SHA:
        raise ValueError('retained independent CPU PROGRAM changed')
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    if (receipt.get('schema') != 'ft_t17_prefix_numeric_launch/v1'
            or receipt.get('rid') != RID or receipt.get('batch') != BATCH
            or receipt.get('cpu_stage_sha256') != CPU_SHA):
        raise ValueError('exact R027 launch receipt required')
    server = Path('/data2/FreeToken/runs/dev_D14') / ('launch_'+RID+'.json')
    if json.loads(server.read_bytes()) != receipt:
        raise ValueError('provided and actual server launch receipts differ')
    directory = Path('/data2/_shared/runs/ft_rounds') / RID
    prior = directory.parent / 'E2-R023-gate-T17' / 'round.json'
    if (sha256(prior) != '92618df52121bf141a6f231d46961d394860ade1b756295b6a5cf6c228c08c1d'
            or json.loads(prior.read_bytes()).get('verdict') != 'not_met'):
        raise ValueError('original T17 not_met counterexample changed')
    if any(p.is_symlink() for p in (directory, *directory.parents, *directory.rglob('*'))):
        raise ValueError('regular evidence paths required')
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        exec(compile(program,
                     'retained_R027_independent_CPU_PROGRAM', 'exec'), {'__name__':'r027_cpu_read'})
    report = json.loads(capture.getvalue())
    if (report['launch_receipt'] != receipt or report['cuda_initialized']
            or not all(report['measurement_binding'].values())):
        raise ValueError('independent runtime/measurement binding differs')
    import torch
    observed = json.loads((directory/'diagnostic_batch55.json').read_bytes())
    numeric_metadata = {}
    for arm, key in (('numeric_warm','warm_prefix'), ('numeric_cold','cold_prefix')):
        prefix = observed[key]
        installed = prefix['installed']
        if (installed['FT_LM_CHUNK'] != '4096'
                or installed['observer_source_sha256'] != receipt['source_files']['t17_prefix_numeric_observe.py']
                or installed['startup_source_sha256'] != receipt['source_files']['t17_prefix_numeric_startup.py']):
            raise ValueError('installed default-chunk source differs')
        final = prefix['final']
        if not (final['valid'] and final['diagnostic_only'] and final['observed_boundary'] == 8192):
            raise ValueError('valid original observation required')
        for segment in prefix['receipt']['segments']:
            for meta in segment['fields'].values():
                coords = {k:segment[k] for k in ('absolute_start','absolute_end','cached_tokens','device_tokens','extend_tokens')}
                if any(meta.get(k) != v for k,v in coords.items()):
                    raise ValueError('tensor and parent segment coordinates differ')
                numeric_metadata[arm+'/numeric/'+meta['file']] = meta
        meta = prefix['receipt']['h']
        numeric_metadata[arm+'/numeric/'+meta['file']] = meta
    paths = {p.relative_to(directory).as_posix():p for p in directory.rglob('*.pt')}
    require_inventory(paths)
    if set(numeric_metadata) != {name for name in paths if '/numeric/' in name}:
        raise ValueError('receipt-owned numeric inventory differs')
    inventory = {}
    for name,path in sorted(paths.items()):
        tensor = torch.load(path, map_location='cpu', weights_only=True)
        if not isinstance(tensor, torch.Tensor):
            raise ValueError('raw tensor file does not contain a tensor')
        item = {'sha256':sha256(path), 'shape':list(tensor.shape), 'dtype':str(tensor.dtype),
                'nbytes':tensor.numel()*tensor.element_size(),
                'role':'compared_shared_prefix' if name in numeric_metadata else 'retained_state_snapshot'}
        if name in numeric_metadata:
            meta = numeric_metadata[name]
            if any(item[k] != meta[k] for k in ('sha256','shape','dtype')):
                raise ValueError('complete numeric tensor provenance differs')
        inventory[name] = item
        del tensor
    report.update(diagnostic_only=True, raw_tensors=inventory,
                  reader_source_sha256=reader_sha or sha256(__file__), companion_source_sha256=COMPANION_SHA,
                  companion_program_sha256=PROGRAM_SHA,
                  reader_mode='retained_program_plus_complete_inventory',
                  quantization={key:observed[key]['receipt']['first_gdn_quantization'] for key in ('warm_prefix','cold_prefix')},
                  limits={'decoder_layer_identity_proved':False, 'kernel_return_h_argument_recorded':False,
                          'donor_snapshot_first_gdn_mapping':'unproved', 'original_T17':'not_met_retained'})
    return report

def remote_read(host, receipt):
    source = Path(__file__).read_text(encoding='utf-8')
    program = companion_program()
    wire = ('import json,os\nos.environ["CUDA_VISIBLE_DEVICES"]=""\nos.environ["PYTHONDONTWRITEBYTECODE"]="1"\n'
            + 'namespace={"__name__":"r027_reader_remote"}\nexec(compile('+repr(source)+',"r027_reader","exec"),namespace)\n'
            + 'print(json.dumps(namespace["read_actual"]('+repr(receipt)+','+repr(program)+','+repr(sha256(__file__))+'),sort_keys=True))\n')
    result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,
                             '/data2/FreeToken/venv/bin/python','-'], input=wire.encode(),capture_output=True,timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-4000:])
    return json.loads(result.stdout)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch-receipt',type=Path,required=True)
    parser.add_argument('--host',default='9');parser.add_argument('--output',type=Path)
    options = parser.parse_args()
    report = remote_read(options.host,json.loads(options.launch_receipt.read_bytes()))
    if options.output:
        with options.output.open('x',encoding='utf-8') as stream:
            json.dump(report,stream,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps({'rid':report['rid'],'cuda_initialized':report['cuda_initialized'],
                      'raw_tensor_count':len(report['raw_tensors']),'comparisons':report['tensor_comparisons']},sort_keys=True))
