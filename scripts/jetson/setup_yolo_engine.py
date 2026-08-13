"""YOLO 모델 준비 파이프라인: .pt 자동 다운로드 → TensorRT export → 구동 확인.

detector_node가 로드하는 ``models/yolov10s.engine``을 명령 한 번으로 만든다.
반드시 Jetson 본체에서 실행할 것 (TensorRT 엔진은 하드웨어·TensorRT 버전 종속).

동작 순서:
    1. ultralytics가 pretrained ``.pt``를 자동 다운로드 (기본 yolov10s.pt)
    2. TensorRT FP16 엔진으로 export (imgsz 640, batch 1)
    3. 저장소 루트 ``models/`` 아래에 ``.engine`` 생성 (.pt/.onnx 중간 산출물 포함)
    4. 엔진을 다시 로드해 더미 프레임 추론으로 구동 확인 (``--skip-verify``로 생략)

사용법 (저장소 안 어디서든):
    python scripts/jetson/setup_yolo_engine.py
    python scripts/jetson/setup_yolo_engine.py --model yolo11n.pt
    python scripts/jetson/setup_yolo_engine.py --force   # 기존 엔진 재변환

전제: JetPack의 TensorRT + ``pip install ultralytics`` (onnx 등 부속 의존성은
ultralytics가 export 시점에 자동 설치를 시도한다).
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_DIR = REPO_ROOT / "models"

logger = logging.getLogger("setup_yolo_engine")


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱한다."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--model",
        default="yolov10s.pt",
        help="ultralytics pretrained 모델 이름 (기본: yolov10s.pt)",
    )
    parser.add_argument(
        "--imgsz", type=int, default=640, help="export 입력 해상도 (기본: 640)"
    )
    parser.add_argument(
        "--models-dir",
        default=str(DEFAULT_MODELS_DIR),
        help="엔진을 둘 디렉토리 (기본: 저장소 루트 models/)",
    )
    parser.add_argument(
        "--force", action="store_true", help="엔진이 이미 있어도 다시 변환"
    )
    parser.add_argument(
        "--skip-verify", action="store_true", help="변환 후 구동 확인 생략"
    )
    return parser.parse_args()


def export_engine(model_name: str, models_dir: Path, imgsz: int, force: bool) -> Path:
    """``.pt``를 (필요 시 다운로드 후) TensorRT FP16 엔진으로 변환한다.

    Args:
        model_name: ultralytics 모델 이름 (예: ``yolov10s.pt``).
        models_dir: ``.pt``·``.engine``이 생성될 디렉토리.
        imgsz: export 입력 해상도.
        force: True면 기존 엔진이 있어도 재변환.

    Returns:
        생성된(또는 이미 있던) ``.engine`` 파일 경로.
    """
    from ultralytics import YOLO  # 지연 import: --help가 무거운 의존성 없이 동작

    models_dir.mkdir(parents=True, exist_ok=True)
    engine_path = models_dir / Path(model_name).with_suffix(".engine").name
    if engine_path.exists() and not force:
        logger.info("이미 존재: %s (재변환하려면 --force)", engine_path)
        return engine_path

    # ultralytics는 없는 .pt를 현재 작업 디렉토리에 다운로드하므로,
    # .pt/.onnx/.engine 산출물이 전부 models/(gitignore됨) 안에 생기게 이동.
    os.chdir(models_dir)
    logger.info("모델 로드/다운로드: %s", model_name)
    model = YOLO(model_name)

    logger.info("TensorRT FP16 export 시작 (imgsz=%d) — 수 분 걸린다", imgsz)
    exported = model.export(
        format="engine",
        device=0,
        half=True,
        imgsz=imgsz,
        batch=1,
        workspace=2,
    )
    exported_path = Path(exported).resolve()
    if exported_path != engine_path.resolve():
        exported_path.replace(engine_path)
    return engine_path


def verify_engine(engine_path: Path, imgsz: int, runs: int = 10) -> None:
    """엔진을 로드해 더미 프레임 추론으로 구동을 확인하고 평균 지연을 로깅한다.

    Args:
        engine_path: 검증할 ``.engine`` 파일 경로.
        imgsz: 추론 입력 해상도 (export와 동일 값 사용).
        runs: 평균을 낼 측정 횟수 (warm-up 3회는 별도).
    """
    import numpy as np
    from ultralytics import YOLO

    model = YOLO(str(engine_path))
    frame = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)

    for _ in range(3):  # warm-up: CUDA 컨텍스트 초기화 시간 배제
        model.predict(frame, classes=[0], verbose=False)

    start = time.perf_counter()
    for _ in range(runs):
        model.predict(frame, classes=[0], verbose=False)
    avg_ms = (time.perf_counter() - start) / runs * 1000.0

    logger.info(
        "구동 확인 OK — 평균 %.1f ms/frame (약 %.1f FPS, 검은 더미 프레임 기준)",
        avg_ms,
        1000.0 / avg_ms,
    )


def main() -> int:
    """파이프라인 실행: 다운로드 → export → models/ 배치 → 구동 확인."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    try:
        engine_path = export_engine(
            args.model, Path(args.models_dir), args.imgsz, args.force
        )
        if args.skip_verify:
            logger.info("--skip-verify: 구동 확인 생략")
        else:
            verify_engine(engine_path, args.imgsz)
    except Exception:
        logger.exception("모델 준비 파이프라인 실패")
        return 1

    logger.info("완료: %s", engine_path)
    logger.info(
        "launch는 저장소 루트 기준 상대 경로 models/%s 로 로드한다 "
        "(follow_robot_launch.py의 model_path 파라미터)",
        engine_path.name,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
