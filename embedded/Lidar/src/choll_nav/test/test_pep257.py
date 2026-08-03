"""ament pep257 독스트링 린트 테스트."""

import pytest
from ament_pep257.main import main


@pytest.mark.linter
@pytest.mark.pep257
def test_pep257() -> None:
    """Docstring 스타일 위반이 없어야 한다."""
    rc = main(argv=[".", "test"])
    assert rc == 0, "Found code style errors / warnings"
