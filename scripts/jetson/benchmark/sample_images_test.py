"""단일 YOLO 모델 스모크 테스트: sample_images/ 추론 후 시각화만 저장."""

import glob
import os

import cv2
from ultralytics import YOLO

model = YOLO("yolo11n.pt")

os.makedirs("result_images", exist_ok=True)

image_paths = glob.glob("sample_images/*.jpg") + glob.glob("sample_images/*.png")

for path in image_paths:
    result = model.predict(path, classes=[0], verbose=False)[0]
    filename = os.path.basename(path)
    annotated = result.plot()  # bbox 그려진 numpy 이미지
    cv2.imwrite(os.path.join("result_images", filename), annotated)

print(f"{len(image_paths)}개 이미지 처리 완료 -> result_images/ 확인하세요")
