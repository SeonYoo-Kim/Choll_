"""Jetson에서 실행: 벤치마크 대상 YOLO .pt 9종을 TensorRT .engine으로 일괄 변환.

⚠️ 알려진 문제: 한 프로세스 안에서 여러 모델을 연속 export하면 몇 개 변환 후
NvMapMemAlloc error 12 (메모리 파편화/부족)로 크래시한다. 실제 벤치마크에서는
이 스크립트 대신 run_export.py(모델당 프로세스 분리)를 사용했다.
역사적 기록 + 소량 변환용으로 보존한다.

주의:
- 반드시 Jetson 본체에서 실행할 것 (TensorRT engine은 하드웨어/버전 종속)
- JetPack에 TensorRT가 이미 설치되어 있어야 함 (Jetson 이미지 기본 포함)
- INT8 변환 시 calibration 데이터셋 필요 (없으면 FP16 권장)

설치:
    pip install ultralytics
"""

from ultralytics import YOLO

MODEL_NAMES = [
    "yolov8n.pt",
    "yolov8s.pt",
    "yolov8m.pt",
    "yolo11n.pt",
    "yolo11s.pt",
    "yolo11m.pt",
    "yolov10n.pt",
    "yolov10s.pt",
    "yolov10m.pt",
]

# FP16: calibration 데이터 없이 바로 가능, 정확도 손실 거의 없음, 속도 이득 큼
# INT8: calibration 데이터셋 필요, 속도는 더 빠르지만 정확도 손실 있을 수 있음
USE_INT8 = False
CALIBRATION_DATA_YAML = "sample_images_calib.yaml"  # INT8 사용 시 준비 필요

for model_name in MODEL_NAMES:
    print(f"변환 중: {model_name}")
    model = YOLO(model_name)

    if USE_INT8:
        model.export(
            format="engine",
            device=0,
            int8=True,
            data=CALIBRATION_DATA_YAML,  # calibration용 이미지 몇백 장 필요
            imgsz=640,
        )
    else:
        model.export(
            format="engine",
            device=0,
            half=True,  # FP16
            imgsz=640,
        )

    print(f"  완료: {model_name.replace('.pt', '.engine')}\n")

print("모든 모델 변환 완료. 같은 폴더에 .engine 파일들 생성됨.")
