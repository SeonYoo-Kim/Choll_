"""Jetson Orin Nano에서 실행: TensorRT .engine 모델들로 runtime + detection 비교.

yolo_benchmark.py와 동일한 로직이지만 .pt 대신 .engine 파일 사용.
export 스크립트(run_export.py 권장)를 먼저 실행해서 weights/ 아래에
.engine 파일들을 준비해둘 것.

설치:
    pip install ultralytics pandas openpyxl
"""

import glob
import os

import cv2
import pandas as pd
from ultralytics import YOLO

# export 스크립트로 미리 변환해둔 .engine 파일 목록
ENGINE_NAMES = [
    "weights/yolov8n.engine",
    "weights/yolov8s.engine",
    "weights/yolov8m.engine",
    "weights/yolo11n.engine",
    "weights/yolo11s.engine",
    "weights/yolo11m.engine",
    "weights/yolov10n.engine",
    "weights/yolov10s.engine",
    "weights/yolov10m.engine",
]

SAMPLE_DIR = "sample_images"
RESULT_ROOT = "result_images_jetson_trt"
PERSON_CLASS = [0]
WARMUP_RUNS = 3  # engine 로드 직후 warm-up (초기 CUDA context 세팅 시간 배제)

image_paths = sorted(
    glob.glob(os.path.join(SAMPLE_DIR, "*.jpg"))
    + glob.glob(os.path.join(SAMPLE_DIR, "*.png"))
)

if not image_paths:
    raise RuntimeError(f"{SAMPLE_DIR}에 jpg/png 이미지가 없습니다.")

print(
    f"총 {len(image_paths)}개 이미지, {len(ENGINE_NAMES)}개 TensorRT 모델 비교 시작\n"
)

summary_rows = []
per_image_rows = []

for engine_name in ENGINE_NAMES:
    if not os.path.exists(engine_name):
        print(f"  {engine_name} 없음, 스킵 (export 스크립트 먼저 실행 필요)")
        continue

    print(f"=== {engine_name} ===")
    model_key = engine_name.replace(".engine", "")
    out_dir = os.path.join(RESULT_ROOT, model_key)
    os.makedirs(out_dir, exist_ok=True)

    model = YOLO(engine_name)  # ultralytics가 .engine 파일도 그대로 로드 가능

    # Warm-up: 첫 몇 회 추론은 캐시/컨텍스트 초기화로 느리므로 측정에서 제외
    for _ in range(WARMUP_RUNS):
        model.predict(image_paths[0], classes=PERSON_CLASS, verbose=False)

    total_preprocess = total_inference = total_postprocess = 0.0
    total_detections = 0
    total_confidence = 0.0
    confidence_count = 0

    for img_path in image_paths:
        result = model.predict(img_path, classes=PERSON_CLASS, verbose=False)[0]

        speed = result.speed
        total_preprocess += speed["preprocess"]
        total_inference += speed["inference"]
        total_postprocess += speed["postprocess"]

        n_det = len(result.boxes)
        total_detections += n_det

        confs = result.boxes.conf.cpu().numpy() if n_det > 0 else []
        for c in confs:
            total_confidence += float(c)
            confidence_count += 1

        annotated = result.plot()
        filename = os.path.basename(img_path)
        cv2.imwrite(os.path.join(out_dir, filename), annotated)

        per_image_rows.append(
            {
                "model": model_key,
                "image": filename,
                "num_detections": n_det,
                "avg_confidence": float(confs.mean()) if n_det > 0 else 0.0,
                "inference_ms": speed["inference"],
            }
        )

    n_images = len(image_paths)
    avg_total_ms = (total_preprocess + total_inference + total_postprocess) / n_images
    summary_rows.append(
        {
            "model": model_key,
            "num_images": n_images,
            "avg_preprocess_ms": total_preprocess / n_images,
            "avg_inference_ms": total_inference / n_images,
            "avg_postprocess_ms": total_postprocess / n_images,
            "avg_total_ms": avg_total_ms,
            "fps_estimate": 1000.0 / avg_total_ms,
            "total_detections": total_detections,
            "avg_detections_per_image": total_detections / n_images,
            "avg_confidence": (
                (total_confidence / confidence_count) if confidence_count > 0 else 0.0
            ),
        }
    )

    print(
        f"  평균 추론시간: {summary_rows[-1]['avg_inference_ms']:.2f} ms, "
        f"FPS 추정: {summary_rows[-1]['fps_estimate']:.1f}\n"
    )

os.makedirs(RESULT_ROOT, exist_ok=True)
summary_df = pd.DataFrame(summary_rows)
detail_df = pd.DataFrame(per_image_rows)

summary_df.to_csv(
    os.path.join(RESULT_ROOT, "model_comparison_summary.csv"), index=False
)
detail_df.to_csv(os.path.join(RESULT_ROOT, "model_comparison_detail.csv"), index=False)

with pd.ExcelWriter(os.path.join(RESULT_ROOT, "model_comparison.xlsx")) as writer:
    summary_df.to_excel(writer, sheet_name="summary", index=False)
    detail_df.to_excel(writer, sheet_name="detail", index=False)

print("완료. 이전 GPU 서버/.pt 결과(result_images/model_comparison_summary.csv)와")
print("이 결과(result_images_jetson_trt/model_comparison_summary.csv)를 비교해보세요.")
