import os
from pathlib import Path
import pytest
from sdk_discriminate import run_arm
@pytest.mark.skipif(not os.getenv('R066C_API_BASE_URL'),reason='live arm only')
def test_live_arm():run_arm(os.environ['R066C_API_BASE_URL'],os.environ['R066C_ARM'],Path(os.environ['R066C_RUN_DIR']),os.environ['R066C_INPUTS_PATH'],os.getenv('R066C_SERVE_LOG'))
