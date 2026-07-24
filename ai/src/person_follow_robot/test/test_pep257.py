"""ament_pep257 docstring style check (run via `colcon test`)."""

import pytest
from ament_pep257.main import main


@pytest.mark.linter
@pytest.mark.pep257
def test_pep257():
    error_count = main(argv=[".", "test"])
    assert error_count == 0, f"Found {error_count} code style errors / warnings"
