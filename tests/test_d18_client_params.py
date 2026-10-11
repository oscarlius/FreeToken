#!/usr/bin/env python3
"""卡D18 单元测试：probe_ft_cold32k.py 参数化后默认请求体与旧版本逐字节相同。

纯 CPU、零依赖：stub 掉 transformers 后按文件路径加载新旧两个版本，
- 常量 MODEL / URL 不变；
- 不传 --url/--model 时 json.dumps(build_payload(...)) 与旧版内联构造逐字节相同；
- extract_overrides 摘除 --url/--model 且不破坏位置参数；
- benchmark_client.py 的 FT_MODEL_NAME 默认值不变（卡D18 第 2 项，现状已满足，防回归）。
"""
import importlib.util
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)  # freetoken/
OLD_PROBE = os.path.join(
    BASE, "plan", "02_开发任务", "d18_artifacts", "probe_ft_cold32k.py.pre_d18"
)
NEW_PROBE = os.path.join(BASE, "scripts", "probe_ft_cold32k.py")
BENCH = os.path.join(os.path.dirname(BASE), "_shared", "benchmark_client.py")

TEXT = "卡D18测试固定文本"


def _load(path, name):
    import importlib.machinery
    sys.modules.setdefault("transformers", types.ModuleType("transformers"))
    sys.modules["transformers"].AutoTokenizer = object
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_constants_unchanged():
    old = _load(OLD_PROBE, "probe_old")
    new = _load(NEW_PROBE, "probe_new")
    assert (old.MODEL, old.URL) == (new.MODEL, new.URL), "MODEL/URL 默认值被改动"


def test_default_body_byte_identical():
    old = _load(OLD_PROBE, "probe_old2")
    new = _load(NEW_PROBE, "probe_new2")
    # 旧版（.pre_d18）main() 内联的 payload 构造，逐行照抄：
    payload_old = {
        "model": old.MODEL,
        "messages": [{"role": "user", "content": TEXT}],
        "max_tokens": 128,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body_old = json.dumps(payload_old).encode("utf-8")
    body_new = json.dumps(
        new.build_payload(new.MODEL, TEXT, 128, False)
    ).encode("utf-8")
    assert body_old == body_new, "默认请求体与旧版本不一致"


def test_nothink_body_byte_identical():
    old = _load(OLD_PROBE, "probe_old3")
    new = _load(NEW_PROBE, "probe_new3")
    payload_old = {
        "model": old.MODEL,
        "messages": [{"role": "user", "content": TEXT}],
        "max_tokens": 64,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    body_old = json.dumps(payload_old).encode("utf-8")
    body_new = json.dumps(
        new.build_payload(new.MODEL, TEXT, 64, True)
    ).encode("utf-8")
    assert body_old == body_new, "nothink 请求体与旧版本不一致"


def test_extract_overrides():
    new = _load(NEW_PROBE, "probe_new4")
    ov, rest = new.extract_overrides([])
    assert ov == {} and rest == []
    ov, rest = new.extract_overrides(
        ["cold1", "32052", "128", "nothink", "--url", "http://127.0.0.1:8085/v1/chat/completions",
         "--model", "some-model"]
    )
    assert ov == {"url": "http://127.0.0.1:8085/v1/chat/completions", "model": "some-model"}
    assert rest == ["cold1", "32052", "128", "nothink"]
    # 值缺失时按位置参数处理（不猜测）
    ov, rest = new.extract_overrides(["--url"])
    assert ov == {} and rest == ["--url"]


def test_benchmark_client_model_env_default():
    assert os.path.exists(BENCH), "benchmark_client.py 不存在"
    src = open(BENCH, encoding="utf-8").read()
    assert 'os.environ.get("FT_MODEL_NAME", "Qwen3.8-Flash-Next-NVFP4")' in src
    assert 'os.environ.get("FT_API_BASE", "http://127.0.0.1:8095/v1")' in src


if __name__ == "__main__":
    for fn in (
        test_constants_unchanged,
        test_default_body_byte_identical,
        test_nothink_body_byte_identical,
        test_extract_overrides,
        test_benchmark_client_model_env_default,
    ):
        fn()
        print("PASS", fn.__name__)
    print("D18 CPU 自检：5/5 PASS")
