# YOLO 모델 벤치마크 (모델 선정 근거)

detector에 쓸 YOLO 모델을 고르기 위해 2026-07 중순에 돌린 비교 스크립트와 결과 기록.
**이 결과를 근거로 YOLOv10s를 채택**했다 (아래 표 참조).

## 스크립트

| 파일 | 용도 | 실행 위치 |
|------|------|-----------|
| [yolo_benchmark.py](yolo_benchmark.py) | `.pt` 9종 비교 (전처리/추론/후처리 ms, conf, 검출 수) | GPU 서버/개발 PC |
| [export_tensorrt_jetson.py](export_tensorrt_jetson.py) | `.pt` 9종 → `.engine` 일괄 변환 (⚠️ 연속 변환 크래시 이력 — 아래 참고) | Jetson |
| [run_export.py](run_export.py) | 위 크래시를 피하는 일괄 변환 드라이버 — 모델마다 [../export_tensorrt_jetson_single.py](../export_tensorrt_jetson_single.py)를 별도 프로세스로 호출 | Jetson |
| [compare_yolo_models_jetson_trt.py](compare_yolo_models_jetson_trt.py) | `.engine` 9종 비교 (warm-up 3회 후 측정) | Jetson |
| [sample_images_test.py](sample_images_test.py) | 단일 모델 스모크 (시각화만 저장) | 아무데나 |

실행 순서 (Jetson 실측 재현 시): `run_export.py` → `compare_yolo_models_jetson_trt.py`.
샘플 이미지는 `sample_images/`에 jpg/png를 직접 넣는다 — 벤치마크 당시 사용한
7장(도서관·사람 장면)은 얼굴이 포함되어 저장소에 커밋하지 않았다 (`*.png`·`*.jpg`는
gitignore 대상이기도 함). 결과 시각화 이미지·xlsx도 같은 이유로 CSV만 커밋.

> `export_tensorrt_jetson.py` 크래시: 한 프로세스에서 여러 모델을 연속 export하면
> NvMapMemAlloc error 12(메모리 파편화)로 죽는다. 실측은 `run_export.py`
> (프로세스 분리)로 진행했다.

## 결과 — Jetson Orin Nano 8GB, TensorRT FP16, imgsz 640, 이미지 7장

[results/model_comparison_summary_jetson_trt.csv](results/model_comparison_summary_jetson_trt.csv) 요약 (소수점 정리):

| 모델 | 추론(ms) | 후처리(ms) | 전체(ms) | FPS 추정 | 검출/이미지 | 평균 conf |
|------|---------:|-----------:|---------:|---------:|------------:|----------:|
| yolov8n | 10.8 | 4.5 | 21.5 | 46.5 | 10.1 | 0.527 |
| yolov8s | 17.3 | 4.7 | 28.2 | 35.4 | 10.1 | 0.545 |
| yolov8m | 32.7 | 6.0 | 45.0 | 22.2 | 10.0 | 0.571 |
| yolo11n | 11.6 | 4.4 | 21.9 | 45.6 | 9.1 | 0.526 |
| yolo11s | 17.7 | 4.5 | 28.3 | 35.4 | 10.3 | 0.535 |
| yolo11m | 30.3 | 5.9 | 42.0 | 23.8 | 9.4 | 0.560 |
| yolov10n | 11.5 | 1.9 | 19.4 | 51.5 | 6.4 | 0.560 |
| **yolov10s** | **18.8** | **2.0** | **26.8** | **37.3** | **8.1** | **0.579** |
| yolov10m | 30.6 | 2.9 | 39.5 | 25.3 | 8.6 | 0.582 |

**yolov10s 선정 이유**: s급 중 평균 confidence 최고(0.579), NMS-free 구조라
후처리가 v8/v11의 절반 이하(2.0ms), 37 FPS로 성능 예산(10 FPS+) 충족.
n급은 더 빠르지만 검출 수·conf가 떨어져 Re-ID 입력 품질이 나빠진다.

- `results/model_comparison_{summary,detail}_jetson_trt.csv` — Jetson TensorRT 실측 (2026-07-20)
- `results/model_comparison_{summary,detail}_pt.csv` — GPU 서버 `.pt` 기준 사전 비교 (2026-07-16)
- ground truth 라벨 없이 proxy 지표(conf·검출 수)로 비교한 것이므로 mAP 아님 (스크립트 docstring 참조)

> `*.csv`는 전역 gitignore 대상이라 이 결과 파일들은 `git add -f`로 커밋되어 있다.
> 재실행으로 갱신할 때도 강제 추가가 필요하다.
