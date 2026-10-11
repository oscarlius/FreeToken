import json, struct, glob, re, collections
d = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"
RULES = [
    ("MTP", lambda k: k.startswith("mtp.")),
    ("视觉", lambda k: k.startswith("model.visual.")),
    ("路由专家", lambda k: ".mlp.experts." in k),
    ("共享专家", lambda k: ".mlp.shared_expert" in k),
    ("路由器", lambda k: ".mlp.gate." in k),
    ("PLE/N-gram", lambda k: ".ple." in k),
    ("GDN", lambda k: ".linear_attn." in k),
    ("全注意力(含indexer)", lambda k: ".self_attn." in k),
    ("超连接", lambda k: "hyper_connection" in k),
    ("embed_tokens", lambda k: "embed_tokens" in k),
    ("lm_head", lambda k: k.startswith("lm_head")),
]
cat = collections.Counter(); other = collections.Counter(); tot = 0; n_t = 0
for f in sorted(glob.glob(d + "/*.safetensors")):
    with open(f, "rb") as h:
        n = struct.unpack("<Q", h.read(8))[0]; H = json.loads(h.read(n))
    for k, v in H.items():
        if k == "__metadata__":
            continue
        b = v["data_offsets"][1] - v["data_offsets"][0]; tot += b; n_t += 1
        c = next((name for name, fn in RULES if fn(k)), None)
        if c is None:
            other[re.sub(r"\.\d+(?=\.|$)", ".N", k)] += b; c = "其他"
        cat[c] += b
print("张量数", n_t, "合计 GiB %.4f" % (tot / 2**30))
for c, b in sorted(cat.items(), key=lambda x: -x[1]):
    print("%-20s %10.4f GiB %16d B" % (c, b / 2**30, b))
print("其他（逐模式）:")
for p, b in sorted(other.items(), key=lambda x: -x[1]):
    print("   %.6f GiB  %s" % (b / 2**30, p))
print("分类合计 == 文件头合计:", sum(cat.values()) == tot)
