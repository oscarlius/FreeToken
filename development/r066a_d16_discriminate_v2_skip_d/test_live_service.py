import os
from pathlib import Path
import pytest
from sdk_adapter import run_service
@pytest.mark.skipif(not os.getenv('R066A_API_BASE_URL'),reason='formal service adapter only')
def test_official_sdk_service(): run_service(os.environ['R066A_API_BASE_URL'],'Qwen3.8-Flash-Next-NVFP4',os.environ['R066A_API_SERVICE'],Path(os.environ['R066A_API_RUN_DIR']))
