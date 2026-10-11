"""Run the explicit D16 sampler CPU suite alongside the reviewed path readers."""
from pathlib import Path

import d16_path_readers_stage as stage


def main() -> None:
    stage.SUITE_SOURCES = (*stage.SUITE_SOURCES, "sampler_capture.py", "retained_state.py")
    stage.TESTS = (*stage.TESTS, "tests/scripts/test_equiv_sampler_capture.py",
                   "tests/scripts/test_equiv_retained_state.py")
    original_sources = stage.source_files

    def sources():
        files = original_sources()
        files["sampler_stage_source.py"] = Path(__file__).read_bytes()
        return files

    stage.source_files = sources
    stage.main()


if __name__ == "__main__":
    main()
