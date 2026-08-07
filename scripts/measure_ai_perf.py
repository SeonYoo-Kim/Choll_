"""AI inference pipeline performance logger (run on the Jetson, alongside the pipeline).

Measures, over fixed windows, and logs to CSV + console:

* FPS        — arrival rate of `/camera/image_raw` (input), `/person_tracks`
               (detector→tracker output, published every processed frame) and
               `/target_person` (final Re-ID output, published while a target
               is locked).
* Latency    — `receive time - header.stamp` in milliseconds. camera_node
               stamps each frame at capture and every downstream node copies
               the header, so this is the full capture→AI-output latency
               including DDS transport, measured on the same host clock.
* Memory     — system RAM used from `/proc/meminfo` (Jetson RAM is unified
               CPU+GPU memory) and the summed RSS of the AI node processes.
               GPU allocations made through NvMap may not appear in RSS, so
               for the "AI memory footprint" claim compare the system value
               against a baseline taken before launching the pipeline and
               pass it via ``--baseline-mb``.

Usage (Jetson, pipeline already running)::

    source /opt/ros/humble/setup.bash
    source ~/Choll/ai/install/setup.bash
    free -m                     # note "used" before launch → --baseline-mb
    python3 scripts/measure_ai_perf.py --duration 120 --baseline-mb 2100

The final summary prints PASS/FAIL against the project targets
(10 FPS+, latency < 100 ms) and is appended to the CSV as `#` comment lines.
Subscribing to the image topic costs a little CPU; pass ``--no-input`` for a
minimal-interference run (FPS/latency of the AI topics are unaffected).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
    from sensor_msgs.msg import Image
    from std_msgs.msg import Header
    from vision_msgs.msg import Detection2DArray
except ImportError as error:  # pragma: no cover - environment guard
    sys.stderr.write(
        "ROS2 환경이 없습니다. Jetson에서 `source /opt/ros/humble/setup.bash` 후 "
        f"실행하세요. (import 실패: {error})\n"
    )
    raise SystemExit(1) from error

FPS_TARGET = 10.0
LATENCY_BUDGET_MS = 100.0
DEFAULT_PROCESS_KEYWORDS = (
    "camera_node",
    "detector_node",
    "tracker_node",
    "reid_node",
    "target_position_node",
    "debug_visualization_node",
)
CSV_COLUMNS = (
    "elapsed_s,input_fps,tracks_fps,target_fps,"
    "tracks_lat_ms_mean,tracks_lat_ms_p95,tracks_lat_ms_max,"
    "target_lat_ms_mean,target_lat_ms_p95,target_lat_ms_max,"
    "ram_used_mb,ram_total_mb,ai_rss_mb"
)


@dataclass
class TopicWindow:
    """Message count and latency samples collected during one window."""

    count: int = 0
    latencies_ms: list[float] = field(default_factory=list)


def _percentile(values: list[float], fraction: float) -> float:
    """Return the linearly interpolated percentile (fraction in 0..1)."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = fraction * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _format_ms(value: float) -> str:
    """Format a latency value for CSV/console, keeping NaN readable."""
    return f"{value:.1f}" if value == value else "nan"


def _read_meminfo_mb() -> tuple[float, float] | None:
    """Return (used_mb, total_mb) from /proc/meminfo, or None off-Linux."""
    try:
        fields: dict[str, float] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            fields[key] = float(rest.strip().split()[0])  # kB
        total = fields["MemTotal"] / 1024.0
        used = total - fields["MemAvailable"] / 1024.0
        return used, total
    except (OSError, KeyError, ValueError, IndexError):
        return None


def _read_ai_rss_mb(keywords: tuple[str, ...]) -> float | None:
    """Return the summed RSS (MB) of processes whose cmdline matches keywords."""
    proc = Path("/proc")
    if not proc.exists():
        return None
    total_kb = 0.0
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode()
            if not any(keyword in cmdline for keyword in keywords):
                continue
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total_kb += float(line.split()[1])
                    break
        except (OSError, ValueError, IndexError):
            continue  # Process exited mid-scan; skip it.
    return total_kb / 1024.0


class PerfMonitorNode(Node):
    """Subscribes to the AI pipeline topics and logs windowed performance."""

    def __init__(self, args: argparse.Namespace) -> None:
        """Set up subscriptions, the CSV file and the window timer."""
        super().__init__("ai_perf_monitor")
        self._interval_s: float = args.interval
        self._duration_s: float = args.duration
        self._baseline_mb: float | None = args.baseline_mb
        self._process_keywords = tuple(args.procs.split(","))
        self._started_at = time.monotonic()
        self.done = False

        self._windows: dict[str, TopicWindow] = {}
        self._total_counts: dict[str, int] = {}
        self._total_latencies: dict[str, list[float]] = {}
        for label in ("input", "tracks", "target"):
            self._windows[label] = TopicWindow()
            self._total_counts[label] = 0
            self._total_latencies[label] = []
        self._peak_ram_used_mb = 0.0
        self._peak_ai_rss_mb = 0.0

        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.create_subscription(
            Detection2DArray, "/person_tracks", self._on_tracks, qos
        )
        self.create_subscription(
            Detection2DArray, "/target_person", self._on_target, qos
        )
        if not args.no_input:
            self.create_subscription(Image, "/camera/image_raw", self._on_input, qos)

        self._output_path = Path(args.output)
        self._file = self._output_path.open("w", encoding="utf-8")
        self._file.write(CSV_COLUMNS + "\n")
        self.create_timer(self._interval_s, self._flush_window)
        self.get_logger().info(
            f"측정 시작 — {self._interval_s:.0f}초 구간, 로그: {self._output_path}"
        )

    def _on_input(self, message: Image) -> None:
        """Count an incoming camera frame (input FPS only)."""
        del message
        self._windows["input"].count += 1

    def _on_tracks(self, message: Detection2DArray) -> None:
        """Record detector→tracker output arrival."""
        self._record("tracks", message.header)

    def _on_target(self, message: Detection2DArray) -> None:
        """Record final Re-ID target output arrival."""
        self._record("target", message.header)

    def _record(self, label: str, header: Header) -> None:
        """Count one message and store its capture→arrival latency."""
        window = self._windows[label]
        window.count += 1
        stamp_ns = header.stamp.sec * 1_000_000_000 + header.stamp.nanosec
        if stamp_ns == 0:
            return  # Unstamped message; latency unknown.
        latency_ms = (self.get_clock().now().nanoseconds - stamp_ns) / 1e6
        window.latencies_ms.append(latency_ms)

    def _flush_window(self) -> None:
        """Emit one CSV row + console line, then reset the window."""
        try:
            elapsed = time.monotonic() - self._started_at
            row = [f"{elapsed:.1f}"]
            console: list[str] = []
            for label in ("input", "tracks", "target"):
                window = self._windows[label]
                fps = window.count / self._interval_s
                row.append(f"{fps:.2f}")
                console.append(f"{label} {fps:.1f}fps")
                self._total_counts[label] += window.count
                self._total_latencies[label].extend(window.latencies_ms)
            for label in ("tracks", "target"):
                samples = self._windows[label].latencies_ms
                mean = statistics.fmean(samples) if samples else float("nan")
                p95 = _percentile(samples, 0.95)
                worst = max(samples) if samples else float("nan")
                row += [_format_ms(mean), _format_ms(p95), _format_ms(worst)]
                console.append(f"{label} lat p95 {_format_ms(p95)}ms")

            meminfo = _read_meminfo_mb()
            ai_rss = _read_ai_rss_mb(self._process_keywords)
            if meminfo is not None:
                used, total = meminfo
                self._peak_ram_used_mb = max(self._peak_ram_used_mb, used)
                row += [f"{used:.0f}", f"{total:.0f}"]
                console.append(f"RAM {used:.0f}/{total:.0f}MB")
            else:
                row += ["nan", "nan"]
            if ai_rss is not None:
                self._peak_ai_rss_mb = max(self._peak_ai_rss_mb, ai_rss)
                row.append(f"{ai_rss:.0f}")
                console.append(f"AI RSS {ai_rss:.0f}MB")
            else:
                row.append("nan")

            self._file.write(",".join(row) + "\n")
            self._file.flush()
            self.get_logger().info(f"[{elapsed:6.1f}s] " + " | ".join(console))
            for label in ("input", "tracks", "target"):
                self._windows[label] = TopicWindow()
            if self._duration_s > 0 and elapsed >= self._duration_s:
                self.done = True
        except Exception as error:  # Keep the monitor alive on any single failure.
            self.get_logger().error(f"측정 구간 기록 실패: {error}")

    def finalize(self) -> None:
        """Print the overall summary and append it to the CSV as comments."""
        elapsed = time.monotonic() - self._started_at
        lines = [f"측정 시간 {elapsed:.1f}s"]
        for label in ("input", "tracks", "target"):
            count = self._total_counts[label] + self._windows[label].count
            self._total_latencies[label].extend(self._windows[label].latencies_ms)
            fps = count / elapsed if elapsed > 0 else float("nan")
            line = f"{label}: {count} msgs, 평균 {fps:.2f} FPS"
            samples = self._total_latencies[label]
            if samples:
                line += (
                    f", 지연 mean {statistics.fmean(samples):.1f}"
                    f" / p50 {_percentile(samples, 0.50):.1f}"
                    f" / p95 {_percentile(samples, 0.95):.1f}"
                    f" / max {max(samples):.1f} ms"
                )
            lines.append(line)
        if self._peak_ram_used_mb > 0:
            ram_line = f"RAM 사용 피크 {self._peak_ram_used_mb:.0f} MB"
            if self._baseline_mb is not None:
                delta = self._peak_ram_used_mb - self._baseline_mb
                ram_line += (
                    f" (파이프라인 전 baseline {self._baseline_mb:.0f} MB"
                    f" → 증가분 {delta:.0f} MB)"
                )
            lines.append(ram_line)
        if self._peak_ai_rss_mb > 0:
            lines.append(f"AI 노드 프로세스 RSS 합 피크 {self._peak_ai_rss_mb:.0f} MB")

        tracks_fps = (
            self._total_counts["tracks"] / elapsed if elapsed > 0 else float("nan")
        )
        latency_pool = (
            self._total_latencies["target"] or self._total_latencies["tracks"]
        )
        p95 = _percentile(latency_pool, 0.95)
        fps_ok = tracks_fps >= FPS_TARGET
        lat_ok = p95 == p95 and p95 < LATENCY_BUDGET_MS
        lines.append(
            f"[{'PASS' if fps_ok else 'FAIL'}] AI FPS {tracks_fps:.2f}"
            f" (목표 {FPS_TARGET:.0f}+, /person_tracks 기준)"
        )
        lines.append(
            f"[{'PASS' if lat_ok else 'FAIL'}] 지연 p95 {_format_ms(p95)} ms"
            f" (목표 < {LATENCY_BUDGET_MS:.0f} ms)"
        )

        summary = "\n".join(lines)
        self.get_logger().info("\n===== 최종 요약 =====\n" + summary)
        for line in lines:
            self._file.write(f"# {line}\n")
        self._file.close()


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--interval", type=float, default=5.0, help="측정 구간 길이(초, 기본 5)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="총 측정 시간(초). 0이면 Ctrl+C까지 계속 (기본 0)",
    )
    parser.add_argument(
        "--output",
        default=time.strftime("ai_perf_%Y%m%d_%H%M%S.csv"),
        help="CSV 로그 경로 (기본: ai_perf_<시각>.csv)",
    )
    parser.add_argument(
        "--baseline-mb",
        type=float,
        default=None,
        help="파이프라인 실행 전 RAM used(MB) — 요약에서 증가분 계산용",
    )
    parser.add_argument(
        "--procs",
        default=",".join(DEFAULT_PROCESS_KEYWORDS),
        help="RSS를 합산할 프로세스 이름 키워드(쉼표 구분)",
    )
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="/camera/image_raw 구독 생략 (측정 부하 최소화)",
    )
    return parser


def main() -> None:
    """Run the monitor until duration elapses or Ctrl+C."""
    args = _build_parser().parse_args()
    rclpy.init()
    node = PerfMonitorNode(args)
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.2)
    except KeyboardInterrupt:
        node.get_logger().info("사용자 중단 — 요약을 생성합니다.")
    finally:
        node.finalize()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
