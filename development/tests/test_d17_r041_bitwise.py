import importlib.util
import json
from pathlib import Path
import pytest

torch = pytest.importorskip("torch")
spec = importlib.util.spec_from_file_location("r041", Path(__file__).parents[1] / "d17_r041_bitwise.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

def fixture(root, *, pid=10, mode="restore", token=1, identity=None, changes=None):
    root.mkdir()
    files = {}
    def put(name, value):
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        files[name] = r.sha(path)
        return path
    inputs = [1] * (8192 + 65)
    tokens = [token] * 128
    put("input.json", {"uid": 7, "input_ids": inputs})
    put("output.json", {"uid": 7, "token_ids": tokens, "text": "full text"})
    put("process.json", {"candidate_commit": "a"*40, "rid": "E2-R041", "case": r.SAMPLE4[0],
                         "process_identity": identity or {"pid": pid, "start_ticks": 100, "execution_id": str(pid)+":100"}})
    roles = {}
    for i, role in enumerate(r.ROLES):
        path = root / (str(i)+".pt")
        torch.save(torch.tensor([0.0, 1.0]), path)
        files[path.name] = r.sha(path)
        roles[role] = {"path": path.name, "sha256": files[path.name]}
    data = {"schema": "ft_r041_restore_diagnostic/v1", "mode": mode, "case": r.SAMPLE4[0],
            "rid": "E2-R041", "candidate_commit": "a"*40, "uid": 7, "coordinate": 8192,
            "input_path": "input.json", "output_path": "output.json", "process_path": "process.json",
            "input_ids_sha256": r.ids_sha(inputs), "token_ids_sha256": r.ids_sha(tokens), "restore_roles": roles}
    data.update(changes or {})
    receipt = put("receipt.json", data)
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"schema": "ft_r041_restore_manifest/v1", "files": files}))
    for path in root.iterdir(): path.chmod(0o444)
    return receipt, {"expected_receipt_sha256": r.sha(receipt), "manifest_path": manifest, "manifest_sha256": r.sha(manifest)}

def test_valid_raw_files_are_diagnostic_only(tmp_path):
    a, aa = fixture(tmp_path/"a")
    b, bb = fixture(tmp_path/"b", pid=20)
    result = r.compare_raw(a, b, left_binding=aa, right_binding=bb)
    assert result["bitwise_equal"] is True and all(result["roles"].values())
    assert result["verdict"] == "indeterminate" and result["admitted"] is False

def test_generated_ids_difference_is_recorded_without_admission(tmp_path):
    a, aa = fixture(tmp_path/"a")
    b, bb = fixture(tmp_path/"b", pid=20, token=2)
    assert r.compare_raw(a, b, left_binding=aa, right_binding=bb)["bitwise_equal"] is False

def test_signed_zero_is_not_bitwise_equal(tmp_path):
    a, aa = fixture(tmp_path/"a")
    b, bb = fixture(tmp_path/"b", pid=20)
    role = b.parent/"0.pt"
    role.chmod(0o644); torch.save(torch.tensor([-0.0, 1.0]), role); role.chmod(0o444)
    receipt = json.loads(b.read_text()); receipt["restore_roles"][r.ROLES[0]]["sha256"] = r.sha(role)
    b.chmod(0o644); b.write_text(json.dumps(receipt)); b.chmod(0o444)
    manifest = bb["manifest_path"]; data = json.loads(manifest.read_text())
    data["files"]["0.pt"] = r.sha(role); data["files"]["receipt.json"] = r.sha(b)
    manifest.chmod(0o644); manifest.write_text(json.dumps(data)); manifest.chmod(0o444)
    bb.update(expected_receipt_sha256=r.sha(b), manifest_sha256=r.sha(manifest))
    result = r.compare_raw(a,b,left_binding=aa,right_binding=bb)
    assert result["roles"][r.ROLES[0]] is False and result["bitwise_equal"] is False

def test_same_process_is_rejected(tmp_path):
    a, aa = fixture(tmp_path/"a")
    b, bb = fixture(tmp_path/"b")
    with pytest.raises(ValueError,match="independent"):
        r.compare_raw(a,b,left_binding=aa,right_binding=bb)

@pytest.mark.parametrize("changes,reason", [
    ({"mode":"donate"},"restore case"), ({"coordinate":False},"coordinate"),
    ({"case":"prefix-1-tail-1"},"restore case"), ({"candidate_commit":"x"*40},"restore case"),
    ({"input_ids_sha256":"0"*64},"input binding"), ({"input_path":"../escape"},"unsafe"),
    ({"input_path":"/tmp/escape"},"unsafe"), ({"restore_roles":{}},"four restore"),
])
def test_bad_receipts_fail_at_their_respective_checks(tmp_path,changes,reason):
    path, binding = fixture(tmp_path/"a", changes=changes)
    with pytest.raises(ValueError,match=reason): r.load_raw(path,**binding)

@pytest.mark.parametrize("value", [True,-1,2**31,"1"])
def test_int32_ids_are_strict(value):
    with pytest.raises(ValueError,match="int32"): r.ids_sha([value])

def test_writable_role_is_rejected(tmp_path):
    path,binding=fixture(tmp_path/"a"); (path.parent/"0.pt").chmod(0o644)
    with pytest.raises(ValueError,match="readonly"):r.load_raw(path,**binding)

def test_external_manifest_tamper_is_rejected(tmp_path):
    path,binding=fixture(tmp_path/"a");binding["manifest_sha256"]="0"*64
    with pytest.raises(ValueError,match="manifest SHA"):r.load_raw(path,**binding)

def test_symlink_ancestor_is_rejected(tmp_path):
    target=tmp_path/"target";target.mkdir();(target/"file").write_text("x");(target/"file").chmod(0o444)
    (tmp_path/"link").symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match="symlink"):r._safe(tmp_path,"link/file")

def test_summary_never_admits():
    assert r.evaluate({"verdict":"kept"})["admitted"] is False
