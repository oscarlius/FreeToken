"""Private-port service owner for R040a's retained native ``Run`` protocol.

Both the formal service and the real-path file dry-run enter ``service`` below.
The latter returns at the exact pre-``Popen`` boundary, after the native arm
files have been created. Nothing in this module contacts the shared endpoint.
"""
from __future__ import annotations

import importlib.util
import json
import socket
from pathlib import Path
from types import MethodType


def private_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as guard:
        guard.bind(("127.0.0.1", 0))
        port = guard.getsockname()[1]
    if not 1024 <= port <= 65535 or port == 8095:
        raise RuntimeError("private socket guard returned an invalid port")
    return port


def make_owner(gpu_module, native_run, lifecycle, options, *, directory=None,
               file_dry_run=False):
    """Construct and bind the reviewed native Run with one private endpoint."""
    owner = native_run(options)
    if directory is not None:
        owner.directory = Path(directory)
    return install(owner, gpu_module=gpu_module, lifecycle=lifecycle,
                   file_dry_run=file_dry_run)


def install(owner, *, gpu_module, lifecycle, file_dry_run=False):
    """Bind a native owner to a dynamic endpoint and its native file protocol."""
    if not callable(getattr(owner, "environment", None)):
        raise TypeError("native owner lacks environment()")
    if not callable(getattr(owner, "compiled_extensions", None)):
        raise TypeError("native owner lacks compiled_extensions()")
    if not file_dry_run and not callable(getattr(lifecycle, "stop_owned_process", None)):
        raise TypeError("formal private owner requires D07 stop_owned_process()")
    if not file_dry_run and (not callable(getattr(lifecycle, 'process_identity', None))
                            or not callable(getattr(lifecycle, 'owned_group_alive', None))):
        raise TypeError('formal private owner requires birth and group checks')
    owner.port = private_port()
    owner.base_url = f"http://127.0.0.1:{owner.port}"
    owner._r040a_private_gpu = gpu_module
    owner._r040a_private_lifecycle = lifecycle
    owner._r040a_file_dry_run = file_dry_run
    owner.service = MethodType(_service, owner)
    owner.gate = MethodType(_private_gate, owner)
    owner.ready = MethodType(_ready, owner)
    owner.ready_health = MethodType(_ready_health, owner)
    owner.request = MethodType(_request, owner)
    owner.stop = MethodType(_stop, owner)
    return owner


def _request(self, arm, label, ids, cached, max_tokens):
    """Keep the native terminal/input receipt checks on the owned endpoint."""
    if self._r040a_file_dry_run:
        raise RuntimeError('CPU file dry-run cannot send a business request')
    gpu = self._r040a_private_gpu
    record = gpu.helper.exact_id_request(self.base_url, ids, max_tokens,
                                       output_path=arm / (label + '.json'),
                                       observations_path=arm / 'observations.jsonl')
    response = gpu.validate_response(record, ids, cached, max_tokens)
    receipt = json.loads((arm / 'inputs' / (str(response['uid']) + '.json')).read_text())
    if (receipt.get('uid') != response['uid'] or receipt.get('numel') != len(ids)
            or receipt.get('int32le_sha256') != gpu.ids_sha(ids)
            or receipt.get('sampling', {}).get('temperature') != 0
            or receipt.get('sampling', {}).get('max_tokens') != max_tokens
            or receipt.get('sampling', {}).get('ignore_eos') is not True):
        raise ValueError('actual tokenizer-worker input receipt differs')
    return response


def _put(gpu, path, value):
    writer = getattr(gpu, "put", None)
    if not callable(writer):
        raise TypeError('retained native metadata writer is unavailable')
    return writer(path, value)


def _command(gpu, argv, **kwargs):
    protocol = getattr(gpu, "protocol", {})
    command = protocol.get("command") if isinstance(protocol, dict) else None
    if not callable(command):
        raise TypeError('retained native command runner is unavailable')
    return command(argv, **kwargs)


def _private_gate(owner, worktree, candidate):
    """Reuse the existing gate that checks source/lock/GPU without port probes."""
    path = Path(__file__).with_name('t16_private_port_base_runner.py')
    spec = importlib.util.spec_from_file_location('r040a_private_gate_base', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Runner.gate(owner, worktree, candidate)


def _environment_report(owner, gpu, source, candidate):
    protocol = getattr(gpu, "protocol", {})
    command = protocol.get("command") if isinstance(protocol, dict) else None
    if not callable(command):
        raise TypeError('retained native environment reporter is unavailable')
    rows = [source, str(candidate), command(["date", "--iso-8601=seconds"]),
            command(["nvidia-smi"]), command(["numactl", "-H"]), command(["free", "-m"])]
    rows.extend(command(["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu"]).splitlines()[:9])
    return "\n".join(rows) + "\n"


def _service(self, name, operation, *, schedule=None, health_only=False,
             max_running_requests=2, mamba_host_slots=0):
    if type(max_running_requests) is not int or max_running_requests not in (2, 4):
        raise ValueError("service capacity must be exactly two or four requests")
    if type(mamba_host_slots) is not int or mamba_host_slots < 0:
        raise ValueError("host bank capacity must be a nonnegative integer")
    if schedule is not None and (not health_only or Path(schedule).is_symlink()
                                 or not Path(schedule).is_file()
                                 or Path(schedule).stat().st_mode & 0o222):
        raise ValueError("scheduled reference requires a frozen file and health-only readiness")
    gpu = self._r040a_private_gpu
    worktree = Path(self.worktree if hasattr(self, 'worktree') else gpu.WT)
    helper = getattr(gpu, "helper")
    candidate = helper.CANDIDATE
    source = self.gate(worktree, candidate)
    extensions = self.compiled_extensions(worktree)
    if hasattr(self, "extensions") and self.extensions != extensions:
        raise ValueError("actually imported compiled extension binding changed between services")
    self.extensions = extensions
    arm = Path(self.directory) / name
    if arm.parent != Path(self.directory) or arm.name != name or name in ('', '.', '..'):
        raise ValueError('native service arm must be a direct child of its output directory')
    arm.mkdir()
    (arm / "inputs").mkdir()
    env = self.environment(worktree, arm, True)
    env.update(CUDA_VISIBLE_DEVICES="0", FT_DEV_STATE_DUMP=str(arm / "dump"),
               FT_T17_INPUT_RECEIPTS=str(arm / "inputs"), FT_T17_OBSERVATIONS=str(arm / "observations.jsonl"))
    if schedule is not None:
        env["FT_DEV_PREFILL_SCHEDULE"] = str(schedule)
    wrapper = self.startup_wrapper()
    for path in (Path(wrapper), Path(gpu.HERE) / 't17_d14_exact_ids.py'):
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
            raise ValueError('test-only startup source is not frozen')
    python = getattr(gpu, "PY", getattr(self, "python", "python"))
    root = Path(getattr(gpu, "ROOT", getattr(self, "root", worktree.parent)))
    argv = ["numactl", "--cpunodebind=0,1", "--interleave=all", str(python), "-u", str(wrapper), "serve",
            "--model-path", str(root / "models/Qwen3.8-Flash-Next-NVFP4-overlay"), "--served-model-name", "Qwen3.8-Flash-Next-NVFP4",
            "--host", "127.0.0.1", "--port", str(self.port), "--memory-ratio", "0.88", "--moe-cache-auto",
            "--moe-prefill-hit-d2d", "--ple-backend", "pinned", "--moe-strategy", "offload", "--quant-backend", "moe.nvfp4=triton",
            "--max-running-requests", str(max_running_requests), "--cuda-graph-max-bs", str(max_running_requests), "--kv-reserve-tokens", "98304",
            "--max-seq-len-override", "98304", "--max-prefill-length", "4096", "--enable-cache-report", "--enable-special-token-ckpt",
            "--tool-call-parser", "qwen3_coder", "--reasoning-parser", "qwen3", "--prefill-layer-major", "--mamba-host-slots", str(mamba_host_slots)]
    _put(gpu, arm / "environment.json", {k: v for k, v in env.items() if k.startswith(("FT_DEV_", "FT_T17_", "FT_D3_", "FT_D16_")) or k in ("PYTHONPATH", "CUDA_VISIBLE_DEVICES")})
    _put(gpu, arm / "compiled_extensions.json", extensions)
    declared = {k: v for k, v in env.items() if k.startswith(("FT_DEV_", "FT_T17_", "FT_D3_", "FT_D16_")) or k in ("PYTHONPATH", "CUDA_VISIBLE_DEVICES", "PATH", "LD_LIBRARY_PATH", "VIRTUAL_ENV")}
    arm.joinpath("SERVE_CMD.txt").write_text(gpu.shlex.join(["env", *[k + "=" + declared[k] for k in sorted(declared)], *argv]) + "\n")
    arm.joinpath("ENV.txt").write_text(_environment_report(self, gpu, source, candidate))
    with arm.joinpath("serve.log").open("x") as log:
        if self._r040a_file_dry_run:
            for name in ('owned_process.json', 'health.json', 'serve_args.txt'):
                _put(gpu, arm / name, {'schema': 'ft_r040a_cpu_file_probe/v1',
                                     'kind': 'CPU_FILE_PROBE', 'not_measurement': True})
            return operation(arm)
        self.proc = gpu.subprocess.Popen(argv, env=env, cwd=worktree, stdout=log, stderr=gpu.subprocess.STDOUT, start_new_session=True)
        try:
            birth = self._r040a_private_lifecycle.process_identity(self.proc.pid)
            if (birth is None or type(birth.get('start_ticks')) is not int or birth['start_ticks'] <= 0
                    or birth.get('pgid') != self.proc.pid or birth.get('session') != self.proc.pid
                    or birth.get('state') == 'Z'):
                raise RuntimeError('private service lacks an owned process birth/group/session')
            self.service_birth = birth
            _put(gpu, arm / 'owned_process.json', {'pid': self.proc.pid, 'pgid': self.proc.pid,
                                                  'port': self.port, 'birth': birth})
            self.set_status(state="loading", arm=name, service_pid=self.proc.pid)
            (self.ready_health if health_only else self.ready)(arm)
            args = self.parser(str(arm / "serve.log"))
            if (args.get("_unique_suffix") != repr(".pid=" + str(self.proc.pid))
                    or args.get("server_port") != str(self.port)
                    or args.get("mamba_host_slots") != str(mamba_host_slots)):
                raise ValueError("parsed owned PID or requested host bank configuration differs")
            arm.joinpath("serve_args.txt").write_text(json.dumps(args, indent=2) + "\n")
            if hasattr(self, "first_args"):
                gpu.protocol["strict_args"](self.first_args, args, {})
            else:
                self.first_args = args
            self.set_status(state="probing", arm=name, service_pid=self.proc.pid)
            return operation(arm)
        finally:
            self.stop()


def _ready_health(self, arm):
    return _ready_common(self, arm, probe=False)


def _ready(self, arm):
    return _ready_common(self, arm, probe=True)


def _ready_common(self, arm, *, probe):
    gpu = self._r040a_private_gpu
    deadline = gpu.time.monotonic() + 600
    while gpu.time.monotonic() < deadline:
        if self.proc.poll() is not None:
            raise RuntimeError("service died during startup")
        try:
            with gpu.urllib.request.urlopen(self.base_url + "/health", timeout=5) as response:
                health = json.load(response)
            if health.get("status") == "error":
                raise RuntimeError("backend error: " + repr(health))
            if health.get("status") == "ok":
                _put(gpu, Path(arm) / "health.json", health)
                break
        except (OSError, gpu.urllib.error.URLError):
            pass
        gpu.time.sleep(5)
    else:
        raise TimeoutError("service readiness exceeded 600s")
    if not probe:
        return
    payload = {"model": "Qwen3.8-Flash-Next-NVFP4", "messages": [{"role": "user", "content": "say ok"}], "max_tokens": 2, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    request = gpu.urllib.request.Request(self.base_url + "/v1/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with gpu.urllib.request.urlopen(request, timeout=25) as response:
        result = json.load(response)
    if "error" in result or not result.get("choices") or not result["choices"][0]["message"].get("content"):
        raise RuntimeError("readiness request failed: " + repr(result))
    _put(gpu, Path(arm) / "ready_sayok.json", result)


def _stop(self):
    if self.proc is None:
        return
    proc = self.proc
    lifecycle = self._r040a_private_lifecycle
    try:
        birth = getattr(self, 'service_birth', None)
        if birth is None:
            raise RuntimeError('service birth is unknown; preserve the enclosing lock')
        current = lifecycle.process_identity(proc.pid)
        if current is not None and any(current.get(k) != birth.get(k)
                                       for k in ('pid', 'start_ticks', 'pgid', 'session')):
            raise RuntimeError('owned service birth changed; preserve the enclosing lock')
        lifecycle.stop_owned_process(proc)
        if lifecycle.owned_group_alive(proc.pid):
            raise RuntimeError('owned process group remains; preserve the enclosing lock')
        gpu = self._r040a_private_gpu
        deadline = gpu.time.monotonic() + 30
        while gpu.time.monotonic() < deadline:
            used = _command(gpu, ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
            if used and all(int(value) < 1000 for value in used.splitlines()):
                self.proc = None
                return
            gpu.time.sleep(2)
        raise RuntimeError('owned service did not release GPU memory')
    except BaseException as error:
        error.owned_cleanup_failed = True
        error.owned_process = proc
        raise
