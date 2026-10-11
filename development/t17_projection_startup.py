"""Install first-layer observation in the retained default-chunk exact-ID startup."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import runpy
import sys

MODEL_CONFIG = Path('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay/config.json')
CONFIG_RESOLVED = Path('/data2/model/Qwen3.8-Flash-Next-NVFP4/config.json.qwen4_exp.orig')
CONFIG_SHA = 'deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80'
PARSER_SOURCE = Path('/data2/FreeToken/wt/e2d14/python/freetoken/models/qwen4_exp/config.py')
PARSER_SHA = '72905266db8c384ea3cd267a1b739c58a32b8b069f37039b778665cc2be14607'


def parse_target_config():
    """Parse the protected served JSON through the candidate parser before Engine/weights."""
    from freetoken.models.qwen4_exp.config import parse_config
    from freetoken.utils import cached_load_hf_config
    source = Path(inspect.getsourcefile(parse_config) or '')
    if (source != PARSER_SOURCE or source.is_symlink() or not source.is_file()
            or hashlib.sha256(source.read_bytes()).hexdigest() != PARSER_SHA):
        raise ValueError('actual candidate config parser differs')
    # Candidate loader falls back to its RawConfigShim for this transformers build's
    # unknown qwen4_exp model_type, then candidate parse_config consumes that real JSON.
    hf = cached_load_hf_config(str(MODEL_CONFIG.parent))
    return hf, parse_config(hf), {'path': str(source), 'sha256': PARSER_SHA,
                                   'qualname': parse_config.__qualname__}


def target_structure():
    resolved = MODEL_CONFIG.resolve(strict=True)
    if resolved != CONFIG_RESOLVED or not resolved.is_file() or hashlib.sha256(resolved.read_bytes()).hexdigest() != CONFIG_SHA:
        raise ValueError('actual target-model configuration changed')
    document = json.loads(MODEL_CONFIG.read_bytes())
    text = document['text_config']
    if (document['architectures'] != ['Qwen4ExpForConditionalGeneration'] or text['num_hidden_layers'] != 48
            or text['ple_layer_ids'] != [2] or len(text['layer_types']) != 48
            or text['layer_types'][0] != 'linear_attention' or text['layer_types'][2] != 'linear_attention'):
        raise ValueError('target GDN/PLE decoder configuration differs')
    hf, parsed, parser = parse_target_config()
    hf_ids = list(hf.text_config.ple_layer_ids)
    parsed_ids = list(parsed.qwen4_args.ple_layer_ids)
    if (hf_ids != text['ple_layer_ids'] or parsed_ids != [1] or parsed.num_layers != 48
            or not parsed.is_linear_layer(1)):
        raise ValueError('candidate parser did not map HF PLE ids to decoder indices')
    return {'path': str(MODEL_CONFIG), 'resolved_source': str(resolved), 'sha256': CONFIG_SHA,
            'parser': parser, 'hf_ple_layer_ids': hf_ids, 'parsed_ple_decoder_indices': parsed_ids,
            'gdn_decoder_index': 0, 'ple_decoder_indices': parsed_ids}


def startup():
    if os.environ.get('FT_LM_CHUNK') != '4096' or not os.environ.get('FT_T17_PROJECTION'):
        raise ValueError('explicit original-chunk projection diagnostic required')
    structure = target_structure()  # Fail before loading model weights or constructing an engine.
    prior = Path(__file__).with_name('t17_original_startup.py')
    if (prior.is_symlink() or prior.stat().st_mode & 0o222
            or hashlib.sha256(prior.read_bytes()).hexdigest() != 'ede1ddb885b7e359838be8aad042ee84f904705aa875be48317ef2452c146b0d'):
        raise ValueError('retained exact-ID startup differs')
    runpy.run_path(str(prior), run_name='ft_projection_original_startup')
    import t17_projection_observe
    from freetoken.core import get_global_ctx
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.io import SchedulerIOMixin
    original_init = Engine.__init__
    original_reply = SchedulerIOMixin._reply_tokenizer_rank0

    def init_projection(self, config):
        original_init(self, config)
        output = Path(os.environ['FT_T17_PROJECTION'])
        output.mkdir(parents=True, exist_ok=True)

        def sink(row):
            with (output / 'observations.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, sort_keys=True) + '\n')

        self._t17_projection = t17_projection_observe.install(
            self.model.model, lambda: get_global_ctx().batch, output_dir=output, sink=sink,
            source_ple_layer_ids=tuple(structure['ple_decoder_indices']))
        with (output / ('installed_' + str(os.getpid()) + '.json')).open('x', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'FT_LM_CHUNK': os.environ['FT_LM_CHUNK'],
                       'output_dir': str(output), 'model': type(self.model.model).__name__, 'model_structure': structure,
                       'decoder_selection': self._t17_projection.selection,
                       'observer_source_sha256': hashlib.sha256(Path(t17_projection_observe.__file__).read_bytes()).hexdigest(),
                       'startup_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, stream, sort_keys=True)
            stream.write('\n')

    def reply_projection(self, messages):
        observer = getattr(self.engine, '_t17_projection', None)
        for message in messages:
            if (observer is not None and observer.identity is not None
                    and type(message).__name__ == 'DetokenizeMsg' and message.finished
                    and str(message.uid) == observer.identity['uid']):
                result = {'uid': str(message.uid), 'positions': list(range(8192, 8257))}
                try:
                    receipt = observer.finalize(message.uid)
                    result.update(valid=True, receipt_file=receipt['receipt_file'],
                                  receipt_sha256=receipt['receipt_sha256'])
                except ValueError as error:
                    result.update(valid=False, error=str(error))
                path = Path(os.environ['FT_T17_PROJECTION']) / ('final_' + str(message.uid) + '.json')
                with path.open('x', encoding='utf-8') as stream:
                    json.dump(result, stream, sort_keys=True)
                    stream.write('\n')
        return original_reply(self, messages)

    Engine.__init__ = init_projection
    SchedulerIOMixin._reply_tokenizer_rank0 = reply_projection


def cpu_worker(queue):
    import t17_d14_exact_ids
    from freetoken.engine.engine import Engine
    from freetoken.server.api_server import app

    class ProofQueue:
        def put(self, result):
            result.update(projection_engine_init=Engine.__init__.__name__, model_structure=target_structure(),
                          exact_endpoint_registered=any(route.path == '/internal/t17/exact-ids' for route in app.routes))
            queue.put(result)

    t17_d14_exact_ids.cpu_probe(ProofQueue())


if __name__ in ('__main__', '__mp_main__'):
    startup()
if __name__ == '__main__':
    if sys.argv[1:] == ['--cpu-startup-probe']:
        import multiprocessing
        context = multiprocessing.get_context('spawn')
        queue = context.Queue()
        process = context.Process(target=cpu_worker, args=(queue,))
        process.start()
        proof = queue.get(timeout=45)
        process.join(45)
        if (process.exitcode != 0 or proof['cuda_initialized'] or proof['ids'] != [1469, 17, 198, 248068]
                or proof['uid'] != 41 or proof['projection_engine_init'] != 'init_projection'
                or not proof['exact_endpoint_registered'] or proof['scheduler_wrapper'] != 'restore_observed'
                or proof['engine_wrapper'] != 'build_chunks_observed' or proof['input_wrapper'] != 'process_observed'
                or proof['reply_wrapper'] != 'reply_projection'
                or proof['model_structure'].get('hf_ple_layer_ids') != [2]
                or proof['model_structure'].get('parsed_ple_decoder_indices') != [1]
                or proof['model_structure'].get('parser', {}).get('sha256') != PARSER_SHA):
            raise ValueError('actual projection startup spawn proof differs')
        print(json.dumps({'schema': 'ft_t17_projection_spawn/v1', 'gpu_started': False, 'worker': proof}, sort_keys=True))
    else:
        from freetoken.cli import main
        sys.argv = ['ft', *sys.argv[1:]]
        main()
