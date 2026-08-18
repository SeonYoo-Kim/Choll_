# 영상 얼굴 모자이크 파이프라인 (face_mosaic)

| 파일 | 용도 |
|---|---|
| `face_mosaic.py` | 영상/이미지 얼굴 자동 모자이크 |
| `vid2gif.py` | 영상의 시간 범위를 지정해 GIF로 변환 (README·문서 삽입용) |
| `yunet.onnx` | YuNet 얼굴 검출 모델 (face_mosaic.py와 같은 폴더에 필요) |

시연 영상 공개 시 개인정보 보호를 위해 **사람 얼굴만** 자동으로 모자이크 처리하는 도구입니다.
Haar Cascade 등 구형 검출기의 고질적인 문제(얼굴 아닌 곳 오탐, 정작 얼굴은 미검출)를
얼굴 전용 검출기 + 트랙 단위 필터링으로 해결했습니다.

## 환경 설정

```bash
conda env create -f environment.yml
conda activate mosaic
```

conda 없이 pip만 쓸 경우:

```bash
pip install -r requirements.txt
```

> `yunet.onnx`(얼굴 검출 모델, 227KB)는 스크립트와 같은 폴더에 있어야 합니다.
> 원본: [opencv_zoo / face_detection_yunet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)

## 사용법

```bash
python face_mosaic.py input.mp4 output.mp4

# Re-ID 디버그 오버레이(바운딩박스·라벨)가 그려진 영상은 라벨을 보호
python face_mosaic.py reID_before.mp4 output.mp4 --protect-overlay

# 이미지(jpg/png/bmp/webp)도 동일하게 처리
python face_mosaic.py screenshot.jpg output.jpg --protect-overlay

# 폴더를 지정하면 안의 모든 이미지/영상을 일괄 처리 (출력도 폴더)
python face_mosaic.py input_folder/ output_folder/ --protect-overlay
```

일괄 처리 시 지원 확장자(jpg/jpeg/png/bmp/webp, mp4/avi/mov/mkv/webm/wmv)만
골라 처리하고 나머지는 건너뜁니다. 입력 폴더와 출력 폴더가 같으면 원본을
덮어쓰지 않도록 `이름_mosaic.확장자`로 저장합니다.

> 이미지 모드에서는 트랙 단위 오탐 필터링(영상 전용)이 불가능하므로
> 검출 결과를 그대로 사용합니다. 오탐이 생기면 `--conf 0.7~0.8`로 올리세요.

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--conf` | 0.6 | 검출 confidence threshold. 얼굴을 놓치면 0.4~0.5로 낮추고, 오탐이 생기면 0.7로 올림 |
| `--margin` | 0.25 | 얼굴 박스 확장 비율. 머리카락·턱까지 덮도록 25% 확장 |
| `--max-gap` | 15 | 검출이 끊겨도 트랙을 유지·보간하는 최대 프레임 수 |
| `--protect-overlay` | off | 영상에 이미 그려진 원색 UI(초록/파랑/빨강 라벨·박스와 내부 흰 글씨)를 모자이크에서 제외 |

## 파이프라인 구조

2-pass 방식으로 동작합니다.

1. **검출** — YuNet(OpenCV `cv2.FaceDetectorYN`)으로 전 프레임 얼굴 검출.
   얼굴 전용 모델이라 옷·배경 오탐이 적고 작은 얼굴도 잡음
2. **트랙 구성** — 프레임 간 박스를 IoU 매칭으로 이어붙여 트랙 생성.
   검출이 끊긴 구간(≤ `max-gap`)은 앞뒤 박스로 선형 보간 → 모자이크 깜빡임 방지
3. **트랙 단위 오탐 필터링** — threshold만으로 못 거르는 오탐(예: 티셔츠 프린팅이
   0.8점까지 나옴)을 트랙 통계로 제거:
   - 실제 검출 횟수 ≥ 3 (단발성 오탐 제거)
   - hit ratio ≥ 0.35 — 진짜 얼굴은 거의 매 프레임 검출(0.8~1.0),
     무늬 오탐은 띄엄띄엄 걸림(<0.3)
   - 검출 점수 중앙값 ≥ 0.72 — 오탐은 일관되게 높은 점수가 안 나옴
4. **트랙 패딩** — 필터를 통과한 트랙의 시작/끝을 6프레임 연장.
   검출기가 얼굴 진입 직후 몇 프레임 늦게 잡아도 노출 방지
5. **렌더링** — 박스를 `margin`만큼 확장 후 다운스케일-업스케일 픽셀화.
   ffmpeg(H.264 재인코딩 + 원본 오디오 복사)는 PATH → `imageio-ffmpeg` 내장
   바이너리 순으로 자동 탐색, 없으면 무음으로 저장

## GIF 변환 (vid2gif.py)

영상의 원하는 구간만 잘라 GIF로 만듭니다. ffmpeg 2-pass 팔레트 방식이라
일반 변환보다 색 품질이 좋습니다.

```bash
# 24초~31초 구간을 GIF로
python vid2gif.py release/reID_mosaic_v2.mp4 demo.gif --start 24 --end 31

# 시간은 mm:ss 형식도 지원, 크기/프레임레이트 조절 가능
python vid2gif.py input.mp4 out.gif --start 1:24 --end 1:31 --fps 15 --width 640
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--start` / `--end` | 0 / 끝까지 | 초(`24`, `24.5`) 또는 `mm:ss`, `hh:mm:ss` |
| `--fps` | 12 | GIF 프레임레이트. 높일수록 부드럽지만 용량 증가 |
| `--width` | 480 | 가로 px (세로는 비율 유지). 원본 크기는 `-1` |

용량이 클 때는 `--width 360`이나 `--fps 10`으로 줄이면 됩니다
(README 삽입용은 3~4MB 이하 권장). 예: 기본 설정으로 7초에 약 5.6MB →
`--width 360 --fps 10`이면 절반 이하로 줄어듭니다.

## 팁

- 파이프라인에 직접 통합할 때는 **모자이크를 먼저 적용하고 그 위에
  바운딩박스/라벨을 그리는 순서**로 하면 `--protect-overlay`가 필요 없음
- 고해상도 영상에서 멀리 있는 아주 작은 얼굴까지 필요하면 검출부만
  insightface의 SCRFD로 교체 가능 (인터페이스 동일하게 유지하면 됨)
