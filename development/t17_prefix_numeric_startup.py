"""Observe the actual first-GDN prefix without changing the engine execution."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys


def startup():
    if os.environ.get('FT_LM_CHUNK') != '4096' or not os.environ.get('FT_T17_PREFIX_NUMERIC'):
        raise ValueError('explicit default-chunk numeric diagnostic required')
    prior = Path(__file__).with_name('t17_original_startup.py')
    if (prior.is_symlink() or prior.stat().st_mode & 0o222
            or hashlib.sha256(prior.read_bytes()).hexdigest() != 'ede1ddb885b7e359838be8aad042ee84f904705aa875be48317ef2452c146b0d'):
        raise ValueError('archived exact-input startup changed')
    runpy.run_path(str(prior), run_name='ft_prefix_numeric_original_startup')
    import t17_prefix_numeric_observe
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.io import SchedulerIOMixin
    original_init = Engine.__init__
    original_reply = SchedulerIOMixin._reply_tokenizer_rank0

    def init_prefix_numeric(self, config):
        original_init(self, config)
        output = Path(os.environ['FT_T17_PREFIX_NUMERIC'])
        output.mkdir(parents=True, exist_ok=True)
        self._t17_prefix_numeric = t17_prefix_numeric_observe.install(
            self.model.model, self.linear_state_pool, output_dir=output, boundary=8192)
        with (output / ('installed_' + str(os.getpid()) + '.json')).open('x', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'FT_LM_CHUNK': os.environ['FT_LM_CHUNK'],
                       'model': type(self.model).__name__, 'diagnostic_only': True,
                       'observer_source_sha256': hashlib.sha256(Path(t17_prefix_numeric_observe.__file__).read_bytes()).hexdigest(),
                       'startup_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, stream, sort_keys=True)
            stream.write('\n')

    def reply_prefix_numeric(self, messages):
        observer = getattr(self.engine, '_t17_prefix_numeric', None)
        for message in messages:
            if (observer is not None and type(message).__name__ == 'DetokenizeMsg'
                    and message.finished and observer.has_uid(message.uid)):
                result = {'uid': str(message.uid), 'observed_boundary': 8192, 'diagnostic_only': True}
                try:
                    receipt = observer.finalize(message.uid)
                    result.update(valid=True, receipt_file=receipt['receipt_file'], receipt_sha256=receipt['receipt_sha256'])
                except ValueError as error:
                    result.update(valid=False, error=str(error))
                with (Path(os.environ['FT_T17_PREFIX_NUMERIC']) / ('final_' + str(message.uid) + '.json')).open('x', encoding='utf-8') as stream:
                    json.dump(result, stream, sort_keys=True);stream.write('\n')
        return original_reply(self, messages)

    Engine.__init__ = init_prefix_numeric
    SchedulerIOMixin._reply_tokenizer_rank0 = reply_prefix_numeric


def cpu_worker(queue):
    import t17_d14_exact_ids
    from freetoken.engine.engine import Engine
    from freetoken.server.api_server import app
    class ProofQueue:
        def put(self, result):
            result.update(numeric_engine_init=Engine.__init__.__name__,
                          exact_endpoint_registered=any(route.path == '/internal/t17/exact-ids' for route in app.routes))
            queue.put(result)
    t17_d14_exact_ids.cpu_probe(ProofQueue())


if __name__ in ('__main__', '__mp_main__'):
    startup()
if __name__ == '__main__':
    if sys.argv[1:] == ['--cpu-startup-probe']:
        import multiprocessing
        context = multiprocessing.get_context('spawn');queue = context.Queue()
        process = context.Process(target=cpu_worker, args=(queue,));process.start()
        proof = queue.get(timeout=45);process.join(45)
        if (process.exitcode != 0 or proof['cuda_initialized'] or proof['ids'] != [1469,17,198,248068]
                or proof['uid'] != 41 or proof['numeric_engine_init'] != 'init_prefix_numeric'
                or not proof['exact_endpoint_registered'] or proof['reply_wrapper'] != 'reply_prefix_numeric'
                or proof['scheduler_wrapper'] != 'restore_observed' or proof['engine_wrapper'] != 'build_chunks_observed'):
            raise ValueError('actual numeric startup spawn proof differs')
        print(json.dumps({'schema':'ft_t17_prefix_numeric_spawn/v1','gpu_started':False,'worker':proof},sort_keys=True))
    else:
        from freetoken.cli import main
        sys.argv = ['ft', *sys.argv[1:]];main()
