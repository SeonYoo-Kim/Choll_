# Jetson 운영 스크립트

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
