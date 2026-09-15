from pathlib import Path

from codegraph_index.config import request_from_project_config


class Config:
    name = "legacy-project"
    language = "python"
    input_paths = [Path("src")]
    test_paths = None
    output_dir = None
    file_patterns = "*.py"
    exclude_patterns = "build tests"
    predefined = ""
    requirements_dir = None


def test_legacy_config_translation_is_explicit_and_immutable(tmp_path):
    request = request_from_project_config(tmp_path, Config())
    assert request.project_id == "legacy-project"
    assert request.repository_id == "legacy-project"
    assert request.file_patterns == ("*.py",)
    assert request.exclude_patterns == ("build", "tests")
