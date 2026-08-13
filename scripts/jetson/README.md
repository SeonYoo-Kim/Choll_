# Jetson 운영 스크립트

## YOLO TensorRT 엔진 변환 (`models/yolov10s.engine` 생성)

detector_node가 로드하는 `models/yolov10s.engine`은 **디바이스 종속**(TensorRT 버전·GPU에 묶임)이라
git에 없고, 새 Jetson 포팅 시 본체에서 직접 변환해야 한다.

**파이프라인 한 번에** — .pt 자동 다운로드 → TensorRT FP16 export → `models/` 배치 → 구동 확인:

```bash
# Jetson에서 (JetPack의 TensorRT 사용, pip install ultralytics 선행)
cd ~/Choll
python scripts/jetson/setup_yolo_engine.py            # 기본 yolov10s.pt
python scripts/jetson/setup_yolo_engine.py --force    # 기존 엔진 재변환
```

끝나면 더미 프레임 추론으로 엔진이 실제로 도는지 확인하고 평균 ms/FPS를 출력한다
(`--skip-verify`로 생략). 이후 바로 `ros2 launch person_follow_robot follow_robot_launch.py`.

수동으로 한 단계씩 하려면 [export_tensorrt_jetson_single.py](export_tensorrt_jetson_single.py):

```bash
cd ~/Choll/scripts/jetson
python export_tensorrt_jetson_single.py yolov10s.pt   # .pt는 ultralytics가 자동 다운로드
mkdir -p ~/Choll/models && mv yolov10s.engine ~/Choll/models/
```

- **모델 하나당 프로세스 하나**로 실행할 것 — 한 프로세스에서 여러 모델을 연속 export하면
  NvMapMemAlloc error 12(메모리 파편화)로 크래시한 이력이 있다 (스크립트 docstring 참조).
- 기본 FP16. INT8은 calibration 데이터셋이 필요해 쓰지 않는다.
- [requirements-jetson.txt](requirements-jetson.txt)는 실제 카트 Jetson의 pip freeze
  (버전 참고용 — torchreid 등 파이프라인 전체 의존성이 다 들어있지는 않다).

## 모델 선정 벤치마크

YOLOv10s를 고르게 된 9종 비교 스크립트·실측 결과(CSV)는 [benchmark/](benchmark/README.md) 참조.

## LiDAR 드라이버 부팅 자동 실행

`ydlidar.service`를 systemd에 등록하면 부팅 시 `ros2 launch ydlidar_ros2_driver
ydlidar_launch.py`가 자동으로 뜬다 (죽으면 5초 후 재시작).

```bash
# 설치 (1회)
sudo cp ~/Choll/scripts/jetson/ydlidar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ydlidar.service

# 상태·로그 확인
systemctl status ydlidar.service
journalctl -u ydlidar.service -f

# 잠깐 끄기 / 자동 실행 해제
sudo systemctl stop ydlidar.service
sudo systemctl disable ydlidar.service
```

확인 방법: 재부팅 후 아무 터미널에서 `ros2 topic hz /scan` — 값이 나오면 성공.

> 전제: ydlidar 워크스페이스가 `~/ydlidar_ros2_ws`에 있고(.bashrc와 동일 경로),
> USB 권한 udev 규칙이 설치돼 있어야 한다(드라이버 설치 시 기본 포함).
> 경로가 다르면 service 파일의 ExecStart를 수정할 것.

메인 파이프라인(follow_robot_launch.py)은 개발 중 재시작·인자 변경이 잦아
수동 실행을 유지한다. 시연 당일에 같은 패턴으로 서비스 하나 더 만들면 된다.
