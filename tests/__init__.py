import atexit
import os
import tempfile

os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

if "MAYBEAI_DATA_DIR" not in os.environ:
    _TEST_DATA_DIR = tempfile.TemporaryDirectory(prefix="maybeai_test_data_", ignore_cleanup_errors=True)
    os.environ["MAYBEAI_DATA_DIR"] = _TEST_DATA_DIR.name
    atexit.register(_TEST_DATA_DIR.cleanup)
