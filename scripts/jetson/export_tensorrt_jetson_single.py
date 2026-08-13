"""
Jetson에서 실행: YOLO .pt 하나를 TensorRT .engine으로 변환 (모델 1개씩, 프로세스 분리 권장)

기존 스크립트가 한 프로세스 안에서 9개 모델을 연속 export하다가
NvMapMemAlloc error 12 (메모리 파편화/부족)로 크래시하는 문제를 해결하기 위해
모델 하나당 별도 프로세스로 실행하도록 변경.

사용법:
    python export_tensorrt_jetson_single.py yolov8n.pt
    python export_tensorrt_jetson_single.py yolov8s.pt
    ... (모델마다 반복)

또는 셸에서 한 번에 순회 (각 호출이 독립 프로세스라 메모리 완전히 정리됨):
    for m in yolov8n yolov8s yolov8m yolo11n yolo11s yolo11m yolov10n yolov10s yolov10m; do
        python export_tensorrt_jetson_single.py ${m}.pt
        sleep 5  # 메모리/전력 안정화 대기
    done
"""

import sys
import gc
import torch
from ultralytics import YOLO

if len(sys.argv) != 2:
    print("사용법: python export_tensorrt_jetson_single.py <model.pt>")
    sys.exit(1)

model_name = sys.argv[1]
USE_INT8 = False
CALIBRATION_DATA_YAML = "sample_images_calib.yaml"

print(f"변환 중: {model_name}")
model = YOLO(model_name)

try:
    if USE_INT8:
        model.export(format="engine", device=0, int8=True,
                     data=CALIBRATION_DATA_YAML, imgsz=640, batch=1, workspace=2)
    else:
        model.export(format="engine", device=0, half=True, imgsz=640, batch=1, workspace=2)
    print(f"완료: {model_name.replace('.pt', '.engine')}")
finally:
    # 명시적 정리 (프로세스 종료로 어차피 정리되지만, 습관적으로 넣어둠)
    del model
    gc.collect()
    torch.cuda.empty_cache()
