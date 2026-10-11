import sys
sys.path.insert(0, r"D:\00.开发\2026\03-模型实验\freetoken")
from phase0_lookup import complete, hit_rate

pr = """Here is my API client:
class Client:
    def get_user(self, id): return self._get(f"/users/{id}")
    def get_order(self, id): return self._get(f"/orders/{id}")
Write get_product, get_payment, delete_user in the same style:"""
out = complete(pr)
gen = out.split("\n", 1)[1] if "\n" in out else out
print("words", len(gen.split()))
print("lookup-hit", round(hit_rate(pr, gen), 3))
