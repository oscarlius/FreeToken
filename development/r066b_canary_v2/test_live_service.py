import os
from pathlib import Path
import pytest
from sdk_adapter import run_service
@pytest.mark.skipif(not os.getenv('R066B_API_BASE_URL'),reason='formal service only')
def test_official_sdk_service():
    run_service(os.environ['R066B_API_BASE_URL'],Path(os.environ['R066B_API_RUN_DIR']),log=Path(os.environ['R066B_SERVE_LOG']))
