import sys
sys.path.insert(0, "python")
sys.path.append("/data2/FreeToken/venv/lib/python3.10/site-packages")
import freetoken
print(freetoken.__file__)
import pytest
raise SystemExit(pytest.main(["-q", "tests/layers/test_route_trace_guard.py", "scripts/tests/test_agent_trace_route_evidence.py", "scripts/tests/test_route_analyze.py"]))
