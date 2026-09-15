import pytest

from codegraph_index.config import ConfigurationError, load_config_file


def test_library_config_errors_are_exceptions(tmp_path):
    with pytest.raises(ConfigurationError, match="configuration file not found"):
        load_config_file(tmp_path)
