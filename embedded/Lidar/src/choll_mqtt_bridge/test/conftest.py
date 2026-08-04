"""pytest 설정 — ROS 미설치 환경에서도 bridge_logic 임포트 가능하게 한다."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
