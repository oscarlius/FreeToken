#!/usr/bin/env python3
"""发布 e3 Q1 演练用桩服务（只用标准库）。不加载模型，不占 GPU，不监听 8095。输出只用于演练，不是测量结果。

- 启动时写出 Parsed arguments（形状与真实 ft serve 的日志相同）。字段只在 argv 中出现时才有，
  因此 argv 漏掉 --prefill-anchor-cut-min-tokens 时，参数门会拒绝。
- /v1/completions 流式请求：先写 Prefill batch 行（段数由 --short-segments / --long-segments 决定），
  再流式输出 128 个 token，然后 finish_reason=length 与 usage，最后 [DONE]。
- prompt 必须与 r065 inputs.json 中 short 或 long 的文本逐字相同，否则返回 400。
- --short-variant B：短请求输出与 A 不同（演练 a 用：短请求 SHA 不等于 e2 参考值）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MODEL = 'Qwen3.8-Flash-Next-NVFP4'
MAX_TOKENS = 128
_PRINT_LOCK = threading.Lock()


def emit(line: str) -> None:
    with _PRINT_LOCK:
        print(line, flush=True)


def parsed_line(argv: list[str]) -> str:
    """与 args.py 的 ServerArgs repr 同形：--name value 变为 name=value，无值的开关记为 True。"""
    fields: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token.startswith('--'):
            name = token[2:].replace('-', '_')
            if index + 1 < len(argv) and not argv[index + 1].startswith('--'):
                fields.append(f'{name}={argv[index + 1]}')
                index += 2
                continue
            fields.append(f'{name}=True')
        index += 1
    return f"ServerArgs(model_path='{MODEL}', {', '.join(fields)})"


def segments(text: str) -> list[int]:
    return [int(part) for part in text.split(',') if part.strip()]


def event(rid: str, created: int, choices: list[dict[str, Any]],
          usage: dict[str, int] | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {'id': rid, 'object': 'text_completion', 'created': created, 'model': MODEL,
                           'choices': choices}
    if usage is not None:
        doc['usage'] = usage
    return doc


class Stub:
    def __init__(self, args: argparse.Namespace) -> None:
        items = json.loads(Path(args.inputs).read_text(encoding='utf-8'))['items']
        self.by_sha = {hashlib.sha256(items[key]['prompt'].encode('utf-8')).hexdigest():
                       (key, items[key]['prompt_tokens']) for key in ('short', 'long')}
        self.short_variant = args.short_variant
        self.segments = {'short': segments(args.short_segments), 'long': segments(args.long_segments)}


class Handler(BaseHTTPRequestHandler):
    server_version = 'op-hak-stub-e3'

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - 保持签名
        return

    def send_json(self, status: int, doc: dict[str, Any]) -> None:
        body = json.dumps(doc, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_event(self, doc: dict[str, Any]) -> None:
        self.wfile.write(b'data: ' + json.dumps(doc, ensure_ascii=False).encode('utf-8') + b'\n\n')
        self.wfile.flush()

    def do_GET(self) -> None:  # noqa: N802 - http.server 的命名
        if self.path != '/health':
            self.send_json(404, {'error': 'not found'})
            return
        self.send_json(200, {'status': 'ok', 'model': MODEL, 'maintenance': 'serving', 'backend_epoch': 0,
                             'restart_attempts': 0, 'restart_waiters': 0})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith('/v1/completions'):
            self.send_json(404, {'error': 'not found'})
            return
        stub: Stub = self.server.stub  # type: ignore[attr-defined]
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('content-length') or 0)))
        except ValueError:
            self.send_json(400, {'error': {'message': 'stub: bad json'}})
            return
        digest = hashlib.sha256(str(body.get('prompt')).encode('utf-8')).hexdigest()
        identified = stub.by_sha.get(digest)
        if identified is None or body.get('stream') is not True or body.get('max_tokens') != MAX_TOKENS:
            self.send_json(400, {'error': {'message': 'stub: prompt or sampling differs from inputs'}})
            return
        key, prompt_tokens = identified
        for new_tokens in stub.segments[key]:
            emit(f'INFO Prefill batch, #new-seq: 1, #new-token: {new_tokens}, #cached-token: 0, token usage: 0.89')
        self.send_response(200)
        self.send_header('content-type', 'text/event-stream')
        self.send_header('cache-control', 'no-cache')
        self.end_headers()
        rid, created = 'cmpl-' + uuid.uuid4().hex, int(time.time())
        prefix = 'B' if key == 'short' and stub.short_variant == 'B' else 't'
        for index in range(MAX_TOKENS):
            self.write_event(event(rid, created, [{'index': 0, 'text': f'{prefix}{index} ',
                                                   'logprobs': None, 'finish_reason': None}]))
        self.write_event(event(rid, created, [{'index': 0, 'text': '', 'logprobs': None,
                                               'finish_reason': 'length'}]))
        self.write_event(event(rid, created, [], usage={'prompt_tokens': prompt_tokens,
                                                        'completion_tokens': MAX_TOKENS,
                                                        'total_tokens': prompt_tokens + MAX_TOKENS}))
        self.wfile.write(b'data: [DONE]\n\n')
        self.wfile.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description='发布 e3 Q1 演练桩服务')
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--argv-json', required=True)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--short-variant', choices=['A', 'B'], default='A')
    parser.add_argument('--short-segments', default='512')
    parser.add_argument('--long-segments', default='8257')
    args = parser.parse_args()
    emit('INFO Parsed arguments:')
    emit(parsed_line(json.loads(args.argv_json)))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.stub = Stub(args)  # type: ignore[attr-defined]
    server.serve_forever()


if __name__ == '__main__':
    main()
