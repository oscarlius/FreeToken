"""CUDA-hidden proof that private instrumentation survives the real spawn interpreter."""
import json
import multiprocessing as mp


def child(queue):
    from freetoken.engine.engine import Engine
    from freetoken.server import api_server
    queue.put({
        "factory_hook": bool(getattr(api_server.run_api_server, "_ft_private_factory_probe", False)),
        "engine_hook": bool(getattr(Engine.forward_batch, "_ft_private_oom_probe", False)),
    })


if __name__ == "__main__":
    context = mp.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=child, args=(queue,))
    process.start()
    try:
        result = queue.get(timeout=60)
        process.join(30)
        assert process.exitcode == 0 and all(result.values()), result
        print(json.dumps(result))
    finally:
        if process.is_alive():
            process.terminate()
            process.join(10)
        queue.close()
