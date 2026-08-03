"""ament flake8 린트 테스트."""

import pytest
from ament_flake8.main import main_with_errors


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8() -> None:
    """flake8 스타일 위반이 없어야 한다."""
    rc, errors = main_with_errors(argv=[])
    assert rc == 0, "Found %d code style errors / warnings:\n" % len(
        errors
    ) + "\n".join(errors)
