import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("d10clean", HERE / "d10_clean_measurement.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def test_filedry_has_one_service_two_synchronised_ignore_eos_requests_and_no_effects():
    value = m.filedry()
    assert value["service"]["count"] == 1
    assert value["barrier"] == {"parties": 2, "release_before_send": True}
    assert len(value["requests"]) == 2 and all(row["ignore_eos"] is True and row["max_tokens"] == 512 for row in value["requests"])
    assert value["warmup"]["paired_d10_steps"] == 16
    assert value["analysis"]["minimum_actual_tokens_per_lane"] == 256
    assert value["side_effects"] == {"popen": False, "http": False, "gpu": False, "gpu_lock": False}


def test_root_admission_is_required_and_unapproved_template_cannot_run(tmp_path):
    path = tmp_path / "admission.json"; path.write_text('{"rid":"E2-D10-CLEAN-MEASURE-20261010","admit":false}')
    try: m.require_admission(path)
    except RuntimeError as exc: assert "sealed root admission required" == str(exc)
    else: raise AssertionError("unapproved admission accepted")

def test_same_uid_warmup_and_shared_window_extracts_lane_tps():
    steps=[{"uids":[7,8],"d10":True,"monotonic_start_ns":i*10,"monotonic_end_ns":i*10+9,"lanes":[{},{}]} for i in range(18)]
    events={7:[{"t_ns":160+i} for i in range(256)],8:[{"t_ns":160+i} for i in range(256)]}
    got=m.extract_shared_window(steps,events)
    assert got["warmup_steps"]==16 and set(got["lane_tps"])=={7,8}

def test_uid_change_is_failed_harness():
    steps=[{"uids":[7,8],"d10":True,"monotonic_start_ns":i*10,"monotonic_end_ns":i*10+9,"lanes":[{},{}]} for i in range(17)]
    steps[-1]["uids"]=[7,9]
    try:m.extract_shared_window(steps,{7:[{"t_ns":1}]*256,8:[{"t_ns":1}]*256})
    except RuntimeError as e:assert "noncontinuous" in str(e)
    else:raise AssertionError("uid replacement accepted")
