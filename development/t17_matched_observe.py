'''Test-only live-state observer for the matched 8192 boundary.'''
from __future__ import annotations
import hashlib, json
from pathlib import Path
import types

ROLES = ('conv_states', 'recurrent_states', 'slot:ple_conv', 'slot:ple_ngram_ctx')

def _copy(value):
    return value.detach().to('cpu').clone()

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Observer:
    def __init__(self, pool, output_dir, boundary=8192, sink=lambda row: None):
        self.pool, self.out, self.boundary, self.sink = pool, Path(output_dir), int(boundary), sink
        self.expected = int(pool.num_linear_layers); self.identity = None
        self.conv, self.recurrent, self.layer_map = {}, {}, {}; self.ple_conv = self.ple_ngram = None
        self.errors = []; self.receipt = None
    def capture(self, layer, batch):
        if not any(int(req.device_len) == self.boundary for req in batch.reqs): return
        if len(batch.reqs) != 1: self.errors.append('boundary batch is not singleton'); return
        req = batch.reqs[0]
        identity = {'uid': str(req.uid), 'slot': int(req.linear_slot_idx),
                    'cached_tokens': int(req.cached_len), 'device_tokens': int(req.device_len),
                    'extend_tokens': int(req.extend_len)}
        if identity['device_tokens'] != self.boundary: return
        if self.identity is None: self.identity = identity
        elif self.identity != identity: self.errors.append('boundary coordinate or request identity drift'); return
        index, slot = int(layer._layer_id), identity['slot']
        if getattr(layer, '_is_linear', False):
            gdn_layer = int(layer.linear_attn.layer_id); local = int(self.pool.local_index(gdn_layer))
            if (index in self.layer_map
                    or local in {item['local_index'] for item in self.layer_map.values()}):
                self.errors.append('duplicate decoder or local GDN capture'); return
            self.conv[index] = _copy(self.pool.conv_states[local, slot])
            self.recurrent[index] = _copy(self.pool.recurrent_states[local, slot])
            self.layer_map[index] = {'decoder_layer_idx':index, 'gdn_layer_id':gdn_layer, 'local_index':local}
            self.sink({'kind':'matched-layer', **identity, **self.layer_map[index], 'module':type(layer).__name__})
        ple = getattr(layer, 'ple', None)
        if ple is not None:
            if self.ple_conv is not None: self.errors.append('duplicate PLE capture'); return
            self.ple_conv = _copy(self.pool.slot_state('ple_conv', ple.layer_id)[slot])
            self.sink({'kind':'matched-ple', **identity, 'layer_idx':index, 'module':type(layer).__name__})
        if len(self.conv) == self.expected and self.ple_ngram is not None: self._assemble()
    def post_commit(self, batch):
        if not any(int(req.device_len) == self.boundary for req in batch.reqs): return
        if len(batch.reqs) != 1: self.errors.append('boundary commit batch is not singleton'); return
        req = batch.reqs[0]
        identity = {'uid': str(req.uid), 'slot': int(req.linear_slot_idx),
                    'cached_tokens': int(req.cached_len), 'device_tokens': int(req.device_len),
                    'extend_tokens': int(req.extend_len)}
        if self.identity != identity: self.errors.append('post-commit boundary identity drift'); return
        if self.ple_ngram is not None: self.errors.append('duplicate PLE ngram post-commit'); return
        self.ple_ngram = _copy(self.pool.slot_state('ple_ngram_ctx')[identity['slot']])
        self.sink({'kind':'matched-ple-ngram', **identity})
        if len(self.conv) == self.expected: self._assemble()
    def _assemble(self):
        if self.receipt is not None or self.errors: return
        if (len(self.recurrent) != self.expected or set(self.conv) != set(self.recurrent)
                or set(x['local_index'] for x in self.layer_map.values()) != set(range(self.expected))):
            self.errors.append('missing or asymmetric GDN layer capture'); return
        if self.ple_conv is None or self.ple_ngram is None:
            self.errors.append('missing PLE boundary capture'); return
        import torch
        self.out.mkdir(parents=True, exist_ok=True); uid = self.identity['uid']
        by_local = {item['local_index']: decoder for decoder, item in self.layer_map.items()}
        tensors = {'conv_states':torch.stack([self.conv[by_local[i]] for i in range(self.expected)]),
                   'recurrent_states':torch.stack([self.recurrent[by_local[i]] for i in range(self.expected)]),
                   'slot:ple_conv':self.ple_conv, 'slot:ple_ngram_ctx':self.ple_ngram}
        roles = {}
        for role, value in tensors.items():
            name = 'matched_%s_%s.pt' % (uid, role.replace(':','_')); path = self.out / name
            if path.exists(): self.errors.append('refusing to replace snapshot'); return
            torch.save(value, path)
            roles[role] = {'file':name, 'sha256':_sha(path), 'shape':list(value.shape), 'dtype':str(value.dtype)}
        receipt = {'schema':'t17_matched_boundary/v1', 'boundary':self.boundary, **self.identity,
                   'linear_layers_by_local':[self.layer_map[by_local[i]] for i in range(self.expected)], 'roles':roles}
        path = self.out / ('matched_%s_receipt.json' % uid)
        with path.open('x', encoding='utf-8') as stream: json.dump(receipt, stream, sort_keys=True, indent=2); stream.write('\n')
        receipt['receipt_file'], receipt['receipt_sha256'] = path.name, _sha(path)
        self.receipt = receipt; self.sink({'kind':'matched-receipt', **receipt})
    def finalize(self):
        self._assemble()
        if self.errors: raise ValueError('; '.join(self.errors))
        if self.receipt is None: raise ValueError('matched boundary has missing layers or was never observed')
        return self.receipt

def install(model, pool, *, output_dir, boundary=8192, sink=lambda row: None):
    observer = Observer(pool, output_dir, boundary, sink)
    for layer in model.layers.op_list:
        if getattr(layer, '_t17_matched_observed', False): raise ValueError('observer already installed')
        original = layer.forward
        def wrapped(this, hidden, batch, _original=original, _layer=layer):
            result = _original(hidden, batch); observer.capture(_layer, batch); return result
        layer.forward = types.MethodType(wrapped, layer); layer._t17_matched_observed = True
    return observer

def wrap_ngram_commit(module, get_batch, observer):
    '''Preserve the real commit exactly once, then observe its outgoing state.'''
    original = module.commit_ngram_context
    def wrapped(meta, fla):
        result = original(meta, fla)
        observer.post_commit(get_batch())
        return result
    module.commit_ngram_context = wrapped
    return original
