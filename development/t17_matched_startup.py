"""Install test-only boundary observation after real engine initialization."""
import json
import hashlib
import os
from pathlib import Path
import runpy
import sys


def startup():
    if os.environ.get('FT_LM_CHUNK') != '7680' or not os.environ.get('FT_T17_MATCHED'):
        raise ValueError('explicit matched-chunk diagnostic environment required')
    original_startup = Path(__file__).with_name('t17_original_startup.py')
    if (original_startup.is_symlink() or original_startup.stat().st_mode & 0o222
            or hashlib.sha256(original_startup.read_bytes()).hexdigest() != 'ede1ddb885b7e359838be8aad042ee84f904705aa875be48317ef2452c146b0d'):
        raise ValueError('archived exact-ID endpoint startup changed')
    runpy.run_path(str(original_startup), run_name='ft_matched_original_startup')
    import t17_matched_observe
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.io import SchedulerIOMixin
    from freetoken.models.qwen4_exp import ple
    from freetoken.core import get_global_ctx
    original_init = Engine.__init__
    original_reply = SchedulerIOMixin._reply_tokenizer_rank0
    original_commit = ple.commit_ngram_context
    active = {}

    def init_matched(self, config):
        original_init(self, config)
        output = Path(os.environ['FT_T17_MATCHED'])
        output.mkdir(parents=True, exist_ok=True)
        def sink(row):
            output.mkdir(parents=True, exist_ok=True)
            with (output / 'observations.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, sort_keys=True) + '\n')
        self._t17_matched = t17_matched_observe.install(
            self.model.model, self.linear_state_pool, output_dir=output, boundary=8192, sink=sink)
        if active:
            raise ValueError('one observed engine per worker required')
        active['observer'] = self._t17_matched
        with (output / ('installed_' + str(os.getpid()) + '.json')).open('x', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'FT_LM_CHUNK': os.environ['FT_LM_CHUNK'],
                       'model': type(self.model).__name__, 'decoder_model': type(self.model.model).__name__,
                       'num_linear_layers': self.linear_state_pool.num_linear_layers,
                       'observer_source_sha256': hashlib.sha256(Path(t17_matched_observe.__file__).read_bytes()).hexdigest(),
                       'startup_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, stream, sort_keys=True)
            stream.write('\n')

    def commit_matched(*args, **kwargs):
        result = original_commit(*args, **kwargs)
        observer = active.get('observer')
        if observer is not None:
            observer.post_commit(get_global_ctx().batch)
        return result

    def reply_matched(self, messages):
        observer = getattr(self.engine, '_t17_matched', None)
        for message in messages:
            if (observer is not None and observer.identity is not None
                    and type(message).__name__ == 'DetokenizeMsg' and message.finished
                    and str(message.uid) == observer.identity['uid']):
                result = {'uid': str(message.uid), 'observed_boundary': 8192}
                try:
                    receipt = observer.finalize()
                    result.update(valid=True, receipt_file=receipt['receipt_file'],
                                  receipt_sha256=receipt['receipt_sha256'])
                except ValueError as error:
                    result.update(valid=False, error=str(error))
                path = Path(os.environ['FT_T17_MATCHED']) / ('final_' + str(message.uid) + '.json')
                with path.open('x', encoding='utf-8') as stream:
                    json.dump(result, stream, sort_keys=True)
                    stream.write('\n')
        return original_reply(self, messages)

    Engine.__init__ = init_matched
    SchedulerIOMixin._reply_tokenizer_rank0 = reply_matched
    ple.commit_ngram_context = commit_matched


def cpu_worker(queue):
    import t17_d14_exact_ids
    from freetoken.engine.engine import Engine
    from freetoken.models.qwen4_exp import ple
    from freetoken.server.api_server import app
    class ProofQueue:
        def put(self, result):
            result.update(matched_engine_init=Engine.__init__.__name__,
                          matched_commit=ple.commit_ngram_context.__name__,
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
        if (process.exitcode != 0 or proof['cuda_initialized'] or proof['ids'] != [1469,17,198,248068]
                or proof['uid'] != 41 or proof['matched_engine_init'] != 'init_matched'
                or proof['matched_commit'] != 'commit_matched' or not proof['exact_endpoint_registered']
                or proof['scheduler_wrapper'] != 'restore_observed' or proof['engine_wrapper'] != 'build_chunks_observed'
                or proof['input_wrapper'] != 'process_observed' or proof['reply_wrapper'] != 'reply_matched'):
            raise ValueError('actual matched startup spawn proof differs')
        print(json.dumps({'schema': 'ft_t17_matched_spawn/v1', 'gpu_started': False, 'worker': proof}, sort_keys=True))
    else:
        from freetoken.cli import main
        sys.argv = ['ft', *sys.argv[1:]]
        main()
