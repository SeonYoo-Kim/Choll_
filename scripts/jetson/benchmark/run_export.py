"""벤치마크용 .pt 일괄 → .engine 변환 드라이버 (모델당 프로세스 분리).

export_tensorrt_jetson.py(한 프로세스 연속 변환)가 NvMapMemAlloc error 12로
크래시하는 문제를 피하려고, 모델마다 export_tensorrt_jetson_single.py를
별도 프로세스로 호출한다. weights/ 아래에 .pt 파일들이 있다고 가정.
"""

import subprocess
import sys
from pathlib import Path

# 한 디렉토리 위의 단일 변환 스크립트를 모델마다 새 프로세스로 실행
SINGLE_EXPORT = Path(__file__).resolve().parent.parent / (
    "export_tensorrt_jetson_single.py"
)

# 변환할 모델 리스트 정의
MODELS = [
    "weights/yolov8m.pt",
    "weights/yolo11n.pt",
    "weights/yolo11s.pt",
    "weights/yolo11m.pt",
    "weights/yolov10n.pt",
    "weights/yolov10s.pt",
    "weights/yolov10m.pt",
]


def main() -> None:
    """모델별로 단일 변환 스크립트를 독립 프로세스로 순차 실행한다."""
    for model in MODELS:
        print("=" * 50)
        print(f">> 변환 시작: {model}")
        print("=" * 50)

        result = subprocess.run([sys.executable, str(SINGLE_EXPORT), model])

        if result.returncode != 0:
            print(f"오류 발생: {model} 변환 실패. 스크립트를 중단합니다.")
            break

    print("모든 모델의 작업이 완료되었습니다!")


if __name__ == "__main__":
    main()
