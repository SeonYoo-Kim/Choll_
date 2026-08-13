"""YOLO 모델 비교 스크립트 (.pt 기준 — GPU 서버/개발 PC용).

- sample_images/ 안의 모든 jpg, png에 대해 여러 YOLO 모델로 predict
- 모델별로 result_images/<model_name>/ 에 시각화 이미지 저장
- 모델별 runtime(전처리/추론/후처리 ms), detection 통계를 CSV(+xlsx)로 저장

주의: ground truth 라벨이 없어서 mAP 같은 진짜 정확도는 계산 불가.
여기서는 proxy 지표(평균 confidence, 이미지당 평균 detection 수)로 비교한다.
정확한 성능 비교가 필요해지면 sample_images 일부에 라벨을 달아
model.val()로 mAP 측정 권장.

설치:
    pip install ultralytics pandas openpyxl
"""

import glob
import os

import cv2
import pandas as pd
from ultralytics import YOLO

# 비교할 모델 목록 (TensorRT export 가능한 Ultralytics 계열)
# 처음 실행 시 자동으로 pretrained 가중치 다운로드됨
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

SAMPLE_DIR = "sample_images"
RESULT_ROOT = "result_images"
PERSON_CLASS = [0]  # COCO person class만 필터링

image_paths = sorted(
    glob.glob(os.path.join(SAMPLE_DIR, "*.jpg"))
    + glob.glob(os.path.join(SAMPLE_DIR, "*.png"))
)

if not image_paths:
    raise RuntimeError(f"{SAMPLE_DIR}에 jpg/png 이미지가 없습니다.")

print(f"총 {len(image_paths)}개 이미지, {len(MODEL_NAMES)}개 모델 비교 시작\n")

summary_rows = []  # 모델당 1행: 전체 요약
per_image_rows = []  # 모델x이미지: 상세 기록

for model_name in MODEL_NAMES:
    print(f"=== {model_name} ===")
    model_key = model_name.replace(".pt", "")
    out_dir = os.path.join(RESULT_ROOT, model_key)
    os.makedirs(out_dir, exist_ok=True)

    try:
        model = YOLO(model_name)
    except Exception as e:  # noqa: BLE001 - 모델 하나 실패해도 비교는 계속
        print(f"  로드 실패, 스킵: {e}")
        continue

    total_preprocess = total_inference = total_postprocess = 0.0
    total_detections = 0
    total_confidence = 0.0
    confidence_count = 0

    for img_path in image_paths:
        result = model.predict(img_path, classes=PERSON_CLASS, verbose=False)[0]

        # ultralytics가 자체 측정한 단계별 시간(ms) 사용 (가장 정확)
        speed = result.speed  # {'preprocess':.., 'inference':.., 'postprocess':..}
        total_preprocess += speed["preprocess"]
        total_inference += speed["inference"]
        total_postprocess += speed["postprocess"]

        n_det = len(result.boxes)
        total_detections += n_det

        confs = result.boxes.conf.cpu().numpy() if n_det > 0 else []
        for c in confs:
            total_confidence += float(c)
            confidence_count += 1

        # 시각화 저장
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
        f"평균 detection/image: {summary_rows[-1]['avg_detections_per_image']:.2f}\n"
    )

# CSV 저장
os.makedirs(RESULT_ROOT, exist_ok=True)
summary_df = pd.DataFrame(summary_rows)
detail_df = pd.DataFrame(per_image_rows)

summary_df.to_csv(
    os.path.join(RESULT_ROOT, "model_comparison_summary.csv"), index=False
)
detail_df.to_csv(os.path.join(RESULT_ROOT, "model_comparison_detail.csv"), index=False)

# 엑셀로도 저장 (요약 + 상세를 시트 2개로)
with pd.ExcelWriter(os.path.join(RESULT_ROOT, "model_comparison.xlsx")) as writer:
    summary_df.to_excel(writer, sheet_name="summary", index=False)
    detail_df.to_excel(writer, sheet_name="detail", index=False)

print("완료:")
print(f"  - 요약: {RESULT_ROOT}/model_comparison_summary.csv")
print(f"  - 상세: {RESULT_ROOT}/model_comparison_detail.csv")
print(f"  - 엑셀: {RESULT_ROOT}/model_comparison.xlsx")
print(f"  - 모델별 시각화: {RESULT_ROOT}/<model_name>/")
