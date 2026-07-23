# Maintenance & Garbage Collection

저장소를 가볍고 재현 가능하게 유지하기 위한 정리(가비지 컬렉션) 정책입니다.
목표: **커밋에는 소스와 문서만. 기계에서 재생성 가능한 산출물은 절대 커밋하지 않는다.**

## 무엇이 "가비지"인가

기기·빌드마다 다시 만들어지며 버전 관리 대상이 아닌 것들:

| 종류 | 경로/패턴 | 왜 제외하나 |
|------|-----------|-------------|
| colcon 빌드 산출물 | `ros2_ws/build/`, `ros2_ws/install/`, `ros2_ws/log/` | `colcon build`로 재생성 |
| Python 캐시 | `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/` | 자동 생성 |
| TensorRT 엔진 | `*.engine`, `*.plan`, `*.trt` | **Orin Nano 기기 종속** — 다른 기기에서 무효 |
| 모델 가중치 | `models/`, `weights/`, `*.pt`, `*.pth`, `*.onnx` | 용량 큼, 외부 배포 |
| 캡처/결과물 | `result.mp4`, `*.mp4`, `*.avi`, `*.jpg`, `*.png`, `output/`, `data/` | 실행 산출물 |
| 가상환경 | `.venv/`, `venv/`, `env/` | 로컬 환경 |

이 패턴들은 [.gitignore](../.gitignore)에 이미 등록되어 있습니다. 새 산출물 종류가 생기면 **먼저 `.gitignore`에 추가**하세요.

## 정리 스크립트

빌드 산출물과 캐시를 지워 클린 상태로 되돌립니다 (소스·문서·모델 가중치는 건드리지 않음):

```bash
bash scripts/gc.sh              # Linux / Jetson / Git Bash
```

```powershell
pwsh scripts/gc.ps1             # Windows PowerShell
```

`--dry-run`으로 무엇이 지워질지 먼저 확인할 수 있습니다:

```bash
bash scripts/gc.sh --dry-run
```

> 스크립트는 **추적되지 않는(untracked) 산출물만** 대상으로 하며, git이 추적 중인 파일은 건드리지 않습니다.
> `result.mp4` 같은 디버그 영상은 실행할 때마다 덮어써지므로 주기적으로 정리하는 것을 권장합니다.

## 컨텍스트/스크래치 위생 (에이전트용)

- 분석·실험용 임시 파일은 저장소가 아니라 세션 스크래치패드에 만든다.
- 커밋 전 `git status`로 의도치 않은 산출물(영상, 엔진, 캐시)이 스테이징되지 않았는지 확인한다.
- 오래된 브랜치·태그·죽은 코드는 발견 즉시 제거하거나 이슈로 남긴다. "언젠가 쓸지도" 코드는 남기지 않는다.

## 주기적 점검 체크리스트

- [ ] `bash scripts/gc.sh --dry-run` 결과에 소스/문서가 없는가
- [ ] `git status`가 깨끗한가 (산출물 미추적)
- [ ] `.gitignore`가 새 산출물 패턴을 포함하는가
- [ ] `ruff check .` / `pytest tests/` 통과하는가
