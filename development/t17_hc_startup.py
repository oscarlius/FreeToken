"""Install the HC observer in the retained original-4096 exact-ID startup."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

from t17_projection_startup import PARSER_SHA, target_structure


ORIGINAL_SHA = 'ede1ddb885b7e359838be8aad042ee84f904705aa875be48317ef2452c146b0d'


def startup():
    if os.environ.get('FT_LM_CHUNK') != '4096' or not os.environ.get('FT_T17_HC'):
        raise ValueError('explicit original-chunk HC diagnostic required')
    structure = target_structure()  # parse protected config before Engine/weights
    prior = Path(__file__).with_name('t17_original_startup.py')
    if prior.is_symlink() or prior.stat().st_mode & 0o222 or hashlib.sha256(prior.read_bytes()).hexdigest() != ORIGINAL_SHA:
        raise ValueError('retained exact-ID startup differs')
    runpy.run_path(str(prior), run_name='ft_hc_original_startup')
    import t17_hc_observe
    from freetoken.core import get_global_ctx
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.io import SchedulerIOMixin
    original_init, original_reply = Engine.__init__, SchedulerIOMixin._reply_tokenizer_rank0

    def init_hc(self, config):
        original_init(self, config)
        output = Path(os.environ['FT_T17_HC'])
        output.mkdir(parents=True, exist_ok=True)
        def sink(row):
            with (output / 'observations.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, sort_keys=True) + '\n')
        self._t17_hc = t17_hc_observe.install(
            self.model.model, lambda: get_global_ctx().batch, output_dir=output, sink=sink,
            parsed_ple_layer_ids=tuple(structure['parsed_ple_decoder_indices']))
        with (output / ('installed_' + str(os.getpid()) + '.json')).open('x', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'FT_LM_CHUNK': '4096', 'output_dir': str(output),
                       'model': type(self.model.model).__name__, 'model_structure': structure,
                       'decoder_selection': self._t17_hc.selection,
                       'observer_source_sha256': hashlib.sha256(Path(t17_hc_observe.__file__).read_bytes()).hexdigest(),
                       'startup_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, stream, sort_keys=True)
            stream.write('\n')

    def reply_hc(self, messages):
        observer = getattr(self.engine, '_t17_hc', None)
        for message in messages:
            if (observer is not None and observer.identity is not None and type(message).__name__ == 'DetokenizeMsg'
                    and message.finished and str(message.uid) == observer.identity['uid']):
                result = {'uid': str(message.uid), 'positions': list(range(4608, 4672))}
                try:
                    receipt = observer.finalize(message.uid)
                    result.update(valid=True, receipt_file=receipt['receipt_file'], receipt_sha256=receipt['receipt_sha256'])
                except ValueError as error:
                    result.update(valid=False, error=str(error))
                with (Path(os.environ['FT_T17_HC']) / ('final_' + str(message.uid) + '.json')).open('x', encoding='utf-8') as stream:
                    json.dump(result, stream, sort_keys=True); stream.write('\n')
        return original_reply(self, messages)

    Engine.__init__, SchedulerIOMixin._reply_tokenizer_rank0 = init_hc, reply_hc


def cpu_worker(queue):
    import t17_d14_exact_ids
    from freetoken.engine.engine import Engine
    from freetoken.server.api_server import app
    class ProofQueue:
        def put(self, result):
            result.update(hc_engine_init=Engine.__init__.__name__, model_structure=target_structure(),
                          exact_endpoint_registered=any(route.path == '/internal/t17/exact-ids' for route in app.routes))
            queue.put(result)
    t17_d14_exact_ids.cpu_probe(ProofQueue())


if __name__ in ('__main__', '__mp_main__'):
    startup()
if __name__ == '__main__':
    if sys.argv[1:] == ['--cpu-startup-probe']:
        import multiprocessing
        context = multiprocessing.get_context('spawn'); queue = context.Queue()
        process = context.Process(target=cpu_worker, args=(queue,)); process.start()
        proof = queue.get(timeout=45); process.join(45)
        if (process.exitcode != 0 or proof['cuda_initialized'] or proof['ids'] != [1469, 17, 198, 248068]
                or proof['uid'] != 41 or proof['hc_engine_init'] != 'init_hc' or not proof['exact_endpoint_registered']
                or proof['scheduler_wrapper'] != 'restore_observed' or proof['engine_wrapper'] != 'build_chunks_observed'
                or proof['input_wrapper'] != 'process_observed' or proof['reply_wrapper'] != 'reply_hc'
                or proof['model_structure'].get('hf_ple_layer_ids') != [2]
                or proof['model_structure'].get('parsed_ple_decoder_indices') != [1]
                or proof['model_structure'].get('parser', {}).get('sha256') != PARSER_SHA):
            raise ValueError('actual HC startup spawn proof differs')
        print(json.dumps({'schema': 'ft_t17_hc_spawn/v1', 'gpu_started': False, 'worker': proof}, sort_keys=True))
    else:
        from freetoken.cli import main
        sys.argv = ['ft', *sys.argv[1:]]; main()
