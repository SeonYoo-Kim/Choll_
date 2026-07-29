"""OSNet Re-ID node with automatic nearest-person target selection.

타겟 선택 (기본: 자동): 바운딩박스 면적이 가장 큰 사람(=가장 가까운 사람)이
auto_select_stable_frames 프레임 연속 최대이면 자동 선택해 등록을 시작한다.
/select_target(Int32)은 수동 오버라이드로 유지 — 대기 상태에서 수동 선택이
먼저 오면 그 id를 사용한다. auto_select_enabled=false면 기존 수동 방식만 동작.
"""

from __future__ import annotations

import copy
import json
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge, CvBridgeError
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Int32, String
from vision_msgs.msg import Detection2D, Detection2DArray

from .reid_logic import accept_recovery, crop_quality_ok
from .target_auto_select import AutoSelectStabilizer, largest_track


class ReIdState(Enum):
    """Runtime states for target selection and Re-ID tracking."""

    WAITING_SELECTION = "waiting_selection"
    INITIALIZING = "initializing"
    TRACKING = "tracking"


@dataclass(frozen=True)
class TrackCandidate:
    """Tracked person candidate paired with its bounding box crop."""

    track_id: int
    detection: Detection2D


@dataclass(frozen=True)
class RecoveryResult:
    """Re-ID recovery output with per-frame similarity debug metrics."""

    candidate: TrackCandidate | None
    candidate_scores: list[tuple[int, float]]
    similarity_count: int
    best_similarity: float


@dataclass(frozen=True)
class FeatureUpdateResult:
    """Memory bank update output with similarity and storage debug metrics."""

    similarity_count: int
    best_similarity: float
    memory_bank_size: int
    memory_bank_feature_count: int


def _get_bbox_center(detection: Detection2D) -> tuple[float, float]:
    """Read BoundingBox2D center across common vision_msgs layouts."""
    center = detection.bbox.center
    if hasattr(center, "position"):
        return float(center.position.x), float(center.position.y)
    return float(center.x), float(center.y)


class MemoryBank:
    """FIFO memory bank for normalized OSNet feature vectors."""

    def __init__(self, max_features: int, similarity_threshold: float) -> None:
        """Set the FIFO capacity and the match-accept threshold."""
        self._features: deque[np.ndarray] = deque(maxlen=max_features)
        self._similarity_threshold = similarity_threshold

    @property
    def size(self) -> int:
        """Return the number of stored target features."""
        return len(self._features)

    @property
    def features(self) -> tuple[np.ndarray, ...]:
        """Return a read-only snapshot of the actual stored feature list."""
        return tuple(self._features)

    def clear(self) -> None:
        """Remove all stored features."""
        self._features.clear()

    def add(self, feature: np.ndarray) -> None:
        """Store one normalized target feature."""
        self._features.append(self._normalize(feature))

    def best_similarity(self, feature: np.ndarray) -> float:
        """Return the best cosine similarity against stored target features."""
        score, _count = self.best_similarity_with_count(feature)
        return score

    def best_similarity_with_count(self, feature: np.ndarray) -> tuple[float, int]:
        """Return best cosine similarity and compared feature count."""
        feature_count = len(self._features)
        if feature_count == 0:
            return -1.0, 0
        normalized = self._normalize(feature)
        return (
            max(float(np.dot(stored, normalized)) for stored in self._features),
            feature_count,
        )

    def is_above_threshold(self, score: float) -> bool:
        """Return whether a similarity score is accepted as target match."""
        return score >= self._similarity_threshold

    def is_match(self, feature: np.ndarray) -> tuple[bool, float]:
        """Return whether a feature matches the bank and its best score."""
        score = self.best_similarity(feature)
        return score >= self._similarity_threshold, score

    @staticmethod
    def _normalize(feature: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(feature))
        if norm <= 0.0:
            raise ValueError("feature vector norm must be greater than zero")
        return (feature / norm).astype(np.float32)


class OsNetFeatureExtractor:
    """OSNet_x1_0 feature extractor using pretrained weights."""

    def __init__(self, device: str) -> None:
        """Lazy-import torch/torchreid and load pretrained OSNet weights."""
        try:
            import torch
            import torchreid
        except ImportError as error:
            raise RuntimeError(
                "torch and torchreid are required for OSNet Re-ID inference. "
                "Install them in the ROS environment before running reid_node."
            ) from error

        self._torch = torch
        if device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = device

        self._model = torchreid.models.build_model(
            name="osnet_x1_0",
            num_classes=1000,
            pretrained=True,
        )
        self._model.to(self._device)
        self._model.eval()

    @property
    def device(self) -> str:
        """Return the active inference device."""
        return self._device

    def extract(self, image: np.ndarray, detection: Detection2D) -> np.ndarray:
        """Crop one tracked person and return a normalized 512-D feature."""
        crop = self._crop_person(image, detection)
        if crop.size == 0:
            raise ValueError("empty person crop")

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (128, 256), interpolation=cv2.INTER_LINEAR)
        tensor = self._to_tensor(resized)

        with self._torch.no_grad():
            feature = self._model(tensor)

        vector = feature.detach().cpu().numpy()[0].astype(np.float32)
        norm = float(np.linalg.norm(vector))
        if norm <= 0.0:
            raise ValueError("OSNet returned a zero feature vector")
        return vector / norm

    def _to_tensor(self, rgb_image: np.ndarray) -> Any:  # noqa: ANN401 — torch 지연 import라 Tensor 타입 명시 불가
        array = rgb_image.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        array = (array - mean) / std
        array = np.transpose(array, (2, 0, 1))[None, ...]
        return self._torch.from_numpy(array).to(self._device)

    @staticmethod
    def crop_size(
        image: np.ndarray | None, detection: Detection2D | None
    ) -> tuple[int, int] | None:
        """Return crop width and height for logging without running inference."""
        if image is None or detection is None:
            return None
        crop = OsNetFeatureExtractor._crop_person(image, detection)
        if crop.size == 0:
            return 0, 0
        height, width = crop.shape[:2]
        return width, height

    @staticmethod
    def _crop_person(image: np.ndarray, detection: Detection2D) -> np.ndarray:
        center_x, center_y = _get_bbox_center(detection)
        half_width = float(detection.bbox.size_x) / 2.0
        half_height = float(detection.bbox.size_y) / 2.0
        height, width = image.shape[:2]

        x1 = max(0, int(round(center_x - half_width)))
        y1 = max(0, int(round(center_y - half_height)))
        x2 = min(width, int(round(center_x + half_width)))
        y2 = min(height, int(round(center_y + half_height)))
        return image[y1:y2, x1:x2]


class ReidNode(Node):
    """Register one selected track and recover it with OSNet Re-ID."""

    def __init__(self) -> None:
        """Declare parameters, load OSNet, and wire the selection pipeline."""
        super().__init__("reid_node")
        self.declare_parameter("registration_duration_sec", 2.0)
        self.declare_parameter("memory_bank_max_features", 20)
        self.declare_parameter("similarity_threshold", 0.85)
        self.declare_parameter("osnet_device", "auto")
        self.declare_parameter("auto_select_enabled", True)
        self.declare_parameter("auto_select_stable_frames", 15)  # 30fps 기준 0.5초
        self.declare_parameter("auto_select_min_area_px", 5000.0)
        self.declare_parameter("feature_sample_interval_sec", 0.3)  # 뱅크 다양성
        self.declare_parameter("recovery_margin", 0.05)  # 1위-2위 최소 격차
        self.declare_parameter("crop_side_margin_px", 4.0)  # 좌우 잘림 판정 여유
        self.declare_parameter("crop_max_area_fraction", 0.5)  # 초근접 배제

        self._registration_duration_sec = float(
            self.get_parameter("registration_duration_sec").value
        )
        max_features = int(self.get_parameter("memory_bank_max_features").value)
        similarity_threshold = float(
            self.get_parameter("similarity_threshold").value
        )
        self._similarity_threshold = similarity_threshold
        self._feature_sample_interval_sec = float(
            self.get_parameter("feature_sample_interval_sec").value
        )
        self._recovery_margin = float(self.get_parameter("recovery_margin").value)
        self._crop_side_margin_px = float(
            self.get_parameter("crop_side_margin_px").value
        )
        self._crop_max_area_fraction = float(
            self.get_parameter("crop_max_area_fraction").value
        )
        self._last_feature_added_at: float | None = None
        osnet_device = str(self.get_parameter("osnet_device").value)
        self._auto_select_enabled = bool(
            self.get_parameter("auto_select_enabled").value
        )
        self._auto_select_min_area_px = float(
            self.get_parameter("auto_select_min_area_px").value
        )
        self._auto_select_stabilizer = AutoSelectStabilizer(
            int(self.get_parameter("auto_select_stable_frames").value)
        )

        self._bridge = CvBridge()
        self._latest_image: np.ndarray | None = None
        self._state = ReIdState.WAITING_SELECTION
        self._target_track_id: int | None = None
        self._registration_started_at: float | None = None
        self._current_track_ids: set[int] = set()
        self._memory_bank = MemoryBank(max_features, similarity_threshold)

        try:
            self._feature_extractor = OsNetFeatureExtractor(osnet_device)
        except RuntimeError as error:
            self.get_logger().fatal(f"Re-ID initialization failed: {error}")
            raise

        self.create_subscription(Image, "/camera/image_raw", self._image_callback, 10)
        self.create_subscription(
            Detection2DArray, "/person_tracks", self._tracks_callback, 10
        )
        self.create_subscription(Int32, "/select_target", self._select_callback, 10)
        self._publisher = self.create_publisher(
            Detection2DArray, "/target_person", 10
        )
        self._recovery_event_publisher = self.create_publisher(
            String, "/reid/recovery_event", 10
        )
        self.get_logger().info(
            "Re-ID node started with OSNet_x1_0 "
            f"(device={self._feature_extractor.device})"
        )
        if self._auto_select_enabled:
            self.get_logger().info(
                "Waiting for target selection (auto-select: largest bbox)"
            )
        else:
            self.get_logger().info("Waiting for target selection")

    def _image_callback(self, message: Image) -> None:
        try:
            self._latest_image = self._bridge.imgmsg_to_cv2(
                message, desired_encoding="bgr8"
            )
        except CvBridgeError as error:
            self.get_logger().error(f"Failed to convert input image: {error}")

    def _tracks_callback(self, message: Detection2DArray) -> None:
        candidates = self._to_candidates(message)
        self._current_track_ids = {candidate.track_id for candidate in candidates}

        if self._state == ReIdState.WAITING_SELECTION:
            if self._auto_select_enabled:
                self._try_auto_select(candidates)
            return

        if self._state == ReIdState.INITIALIZING:
            self._handle_initializing(candidates)
            return

        self._handle_tracking(message, candidates)

    def _select_callback(self, message: Int32) -> None:
        selected_id = int(message.data)
        if self._state != ReIdState.WAITING_SELECTION:
            self.get_logger().warn(
                "Ignoring target selection while Re-ID is not waiting "
                f"(state={self._state.value}, requested_id={selected_id})"
            )
            return

        if selected_id not in self._current_track_ids:
            available_ids = sorted(self._current_track_ids)
            self.get_logger().warn(
                f"Rejected target ID={selected_id}: not currently tracked "
                f"(available={available_ids})"
            )
            return

        self._start_memory_bank_initialization(selected_id)

    def _try_auto_select(self, candidates: list[TrackCandidate]) -> None:
        """가장 큰 bbox 트랙이 연속으로 관찰되면 자동 선택한다.

        잘리거나 초근접인 bbox는 후보에서 제외한다 — 그런 크롭으로 등록하면
        Memory Bank가 몸통 조각으로 오염되어 재인식이 망가진다.
        """
        if self._latest_image is None:
            return  # 등록에 이미지가 필요하므로 이미지 수신 전에는 선택 보류
        track_areas = [
            (
                candidate.track_id,
                float(candidate.detection.bbox.size_x)
                * float(candidate.detection.bbox.size_y),
            )
            for candidate in candidates
            if self._crop_quality_ok(candidate)
        ]
        nearest_id = largest_track(track_areas, self._auto_select_min_area_px)
        confirmed_id = self._auto_select_stabilizer.observe(nearest_id)
        if confirmed_id is None:
            return

        self.get_logger().info(
            f"Auto-selected nearest person: ID={confirmed_id} "
            f"(largest bbox for {self._auto_select_stabilizer.consecutive_frames} "
            "consecutive frames)"
        )
        self._auto_select_stabilizer.reset()
        self._start_memory_bank_initialization(confirmed_id)

    def _crop_quality_ok(self, candidate: TrackCandidate) -> bool:
        """후보 bbox가 Re-ID 피처로 쓸 만한 크롭인지 판정한다."""
        image = self._latest_image
        if image is None:
            return False
        image_height, image_width = image.shape[:2]
        center_x, center_y = _get_bbox_center(candidate.detection)
        return crop_quality_ok(
            center_x,
            center_y,
            float(candidate.detection.bbox.size_x),
            float(candidate.detection.bbox.size_y),
            float(image_width),
            float(image_height),
            self._crop_side_margin_px,
            self._crop_max_area_fraction,
        )

    def _start_memory_bank_initialization(self, selected_id: int) -> None:
        self._target_track_id = selected_id
        self._registration_started_at = time.monotonic()
        self._last_feature_added_at = None  # 첫 피처는 즉시 수집
        self._memory_bank.clear()
        self._state = ReIdState.INITIALIZING
        self.get_logger().info(f"Target selected: ID={selected_id}")
        self.get_logger().info("Initializing Memory Bank...")

    def _handle_initializing(self, candidates: list[TrackCandidate]) -> None:
        if self._target_track_id is None or self._registration_started_at is None:
            self._reset_to_selection("missing target state during initialization")
            return

        target = self._find_candidate(candidates, self._target_track_id)
        if target is not None:
            self._add_target_feature(target)

        elapsed = time.monotonic() - self._registration_started_at
        if elapsed < self._registration_duration_sec:
            return

        if self._memory_bank.size == 0:
            self._reset_to_selection(
                "Memory Bank initialization failed: no target features collected"
            )
            return

        actual_feature_count = len(self._memory_bank.features)
        self._state = ReIdState.TRACKING
        self.get_logger().info(
            f"Memory Bank initialized ({self._memory_bank.size} features)"
        )
        self.get_logger().info(
            "Memory Bank debug: "
            f"size_property={self._memory_bank.size}, "
            f"actual_feature_count={actual_feature_count}"
        )
        self.get_logger().info("Switched to normal tracking mode")

    def _handle_tracking(
        self,
        message: Detection2DArray,
        candidates: list[TrackCandidate],
    ) -> None:
        if self._target_track_id is None:
            self._reset_to_selection("missing target ID during tracking")
            return

        track_ids = sorted(candidate.track_id for candidate in candidates)
        target = self._find_candidate(candidates, self._target_track_id)
        if target is not None:
            feature_update = self._add_target_feature(target)
            self._log_tracking_debug(
                track_ids=track_ids,
                target_candidate_found=True,
                crop_candidate=target,
                similarity_count=(
                    0 if feature_update is None else feature_update.similarity_count
                ),
                best_similarity=(
                    -1.0 if feature_update is None else feature_update.best_similarity
                ),
                memory_bank_size=(
                    self._memory_bank.size
                    if feature_update is None
                    else feature_update.memory_bank_size
                ),
                memory_bank_feature_count=(
                    len(self._memory_bank.features)
                    if feature_update is None
                    else feature_update.memory_bank_feature_count
                ),
                throttle_duration_sec=2.0,
            )
            self._publish_target(message, target)
            return

        self.get_logger().warn(
            "Target lost: "
            f"target_track_id={self._target_track_id}, "
            f"current_track_ids={track_ids}"
        )
        recovery = self._recover_target(candidates)
        self._log_tracking_debug(
            track_ids=track_ids,
            target_candidate_found=False,
            crop_candidate=recovery.candidate,
            similarity_count=recovery.similarity_count,
            best_similarity=recovery.best_similarity,
            memory_bank_size=self._memory_bank.size,
            memory_bank_feature_count=len(self._memory_bank.features),
            throttle_duration_sec=None,
        )
        if recovery.candidate is None:
            self.get_logger().warn(
                "Recovery Failure: no candidate exceeded similarity threshold "
                f"(best_similarity={recovery.best_similarity:.3f})"
            )
            return

        self._target_track_id = recovery.candidate.track_id
        self._publish_target(message, recovery.candidate)
        self._publish_recovery_event(
            recovery.candidate.track_id,
            recovery.best_similarity,
        )
        self._add_target_feature(recovery.candidate, force=True)
        self.get_logger().info(
            f"Recovery Success: Recovered target as Track ID={self._target_track_id}"
        )
        self.get_logger().info(
            f"/target_person published with Track ID={self._target_track_id}"
        )

    def _recover_target(self, candidates: list[TrackCandidate]) -> RecoveryResult:
        image = self._latest_image
        if image is None:
            self.get_logger().warn(
                "Cannot run Re-ID recovery before receiving camera image",
                throttle_duration_sec=1.0,
            )
            return RecoveryResult(None, [], 0, -1.0)

        best_candidate: TrackCandidate | None = None
        best_score = -1.0
        candidate_scores: list[tuple[int, float]] = []
        similarity_count = 0
        self.get_logger().info(
            "Recovery Candidate IDs: "
            f"{[candidate.track_id for candidate in candidates]}"
        )
        for candidate in candidates:
            try:
                feature = self._feature_extractor.extract(image, candidate.detection)
                score, compared_count = self._memory_bank.best_similarity_with_count(
                    feature
                )
            except (RuntimeError, ValueError) as error:
                self.get_logger().warn(f"Failed to extract candidate feature: {error}")
                continue

            similarity_count += compared_count
            candidate_scores.append((candidate.track_id, score))
            self.get_logger().info(
                f"Candidate {candidate.track_id} similarity={score:.3f}"
            )
            if score > best_score:
                best_candidate = candidate
                best_score = score

        best_id = None if best_candidate is None else best_candidate.track_id
        self.get_logger().info(
            f"Best Candidate: ID={best_id}, similarity={best_score:.3f}"
        )
        accepted_id = accept_recovery(
            candidate_scores, self._similarity_threshold, self._recovery_margin
        )
        if accepted_id is None:
            if best_candidate is not None and best_score >= self._similarity_threshold:
                # 임계값은 넘었지만 2위와의 격차 부족 → 오인 방지 위해 보류
                self.get_logger().info(
                    "Recovery Failure: ambiguous match, runner-up within margin "
                    f"(best={best_score:.3f}, margin={self._recovery_margin})"
                )
            else:
                self.get_logger().info(
                    f"Recovery Failure: best similarity below threshold "
                    f"(best={best_score:.3f})"
                )
            return RecoveryResult(None, candidate_scores, similarity_count, best_score)

        accepted = self._find_candidate(candidates, accepted_id)
        self.get_logger().info(
            f"Recovery match accepted: ID={accepted_id}, "
            f"similarity={best_score:.3f}"
        )
        return RecoveryResult(
            accepted,
            candidate_scores,
            similarity_count,
            best_score,
        )

    def _log_tracking_debug(
        self,
        track_ids: list[int],
        target_candidate_found: bool,
        crop_candidate: TrackCandidate | None,
        similarity_count: int,
        best_similarity: float,
        memory_bank_size: int,
        memory_bank_feature_count: int,
        throttle_duration_sec: float | None,
    ) -> None:
        crop_size = OsNetFeatureExtractor.crop_size(
            self._latest_image,
            None if crop_candidate is None else crop_candidate.detection,
        )
        crop_size_text = (
            "none" if crop_size is None else f"{crop_size[0]}x{crop_size[1]}"
        )
        log_message = (
            "TRACKING debug: "
            f"target_track_id={self._target_track_id}, "
            f"track_ids={track_ids}, "
            f"target_candidate_found={target_candidate_found}, "
            f"crop_size={crop_size_text}, "
            f"similarity_count={similarity_count}, "
            f"best_similarity={best_similarity:.3f}, "
            f"memory_bank_size={memory_bank_size}, "
            f"memory_bank_feature_count={memory_bank_feature_count}"
        )
        if throttle_duration_sec is None:
            self.get_logger().info(log_message)
            return
        self.get_logger().info(
            log_message,
            throttle_duration_sec=throttle_duration_sec,
        )

    def _add_target_feature(
        self, candidate: TrackCandidate, force: bool = False
    ) -> FeatureUpdateResult | None:
        image = self._latest_image
        if image is None:
            self.get_logger().warn(
                "Skipping feature extraction: no camera image received yet",
                throttle_duration_sec=1.0,
            )
            return None

        # 샘플링 간격: 매 프레임 추가하면 FIFO 뱅크가 최근 0.7초의 동일한
        # 모습으로만 채워져 재인식이 망가진다. 간격을 두어 다양성을 확보.
        # (재탐색 성공 직후는 force=True — 새 각도의 피처를 즉시 반영)
        now = time.monotonic()
        if (
            not force
            and self._last_feature_added_at is not None
            and now - self._last_feature_added_at < self._feature_sample_interval_sec
        ):
            return None

        # 잘리거나 초근접인 크롭은 뱅크를 오염시키므로 건너뛴다
        if not self._crop_quality_ok(candidate):
            return None

        try:
            feature = self._feature_extractor.extract(image, candidate.detection)
            best_similarity, similarity_count = (
                self._memory_bank.best_similarity_with_count(feature)
            )
            self._memory_bank.add(feature)
            self._last_feature_added_at = now
            return FeatureUpdateResult(
                similarity_count=similarity_count,
                best_similarity=best_similarity,
                memory_bank_size=self._memory_bank.size,
                memory_bank_feature_count=len(self._memory_bank.features),
            )
        except (RuntimeError, ValueError) as error:
            self.get_logger().warn(f"Failed to add target feature: {error}")
            return None

    def _publish_target(
        self, source: Detection2DArray, candidate: TrackCandidate
    ) -> None:
        output = Detection2DArray()
        output.header = source.header
        output.detections = [copy.deepcopy(candidate.detection)]
        self._publisher.publish(output)

    def _publish_recovery_event(self, track_id: int, similarity: float) -> None:
        message = String()
        message.data = json.dumps({
            "track_id": track_id,
            "similarity": similarity,
            "event": "recovered",
        })
        self._recovery_event_publisher.publish(message)

    def _reset_to_selection(self, reason: str) -> None:
        self.get_logger().error(reason)
        self._target_track_id = None
        self._registration_started_at = None
        self._memory_bank.clear()
        self._auto_select_stabilizer.reset()
        self._state = ReIdState.WAITING_SELECTION
        if self._auto_select_enabled:
            self.get_logger().info(
                "Waiting for target selection (auto-select: largest bbox)"
            )
        else:
            self.get_logger().info("Waiting for target selection")

    @staticmethod
    def _to_candidates(message: Detection2DArray) -> list[TrackCandidate]:
        candidates: list[TrackCandidate] = []
        for detection in message.detections:
            try:
                track_id = int(detection.id)
            except (TypeError, ValueError):
                continue
            candidates.append(TrackCandidate(track_id, detection))
        return candidates

    @staticmethod
    def _find_candidate(
        candidates: list[TrackCandidate], track_id: int
    ) -> TrackCandidate | None:
        for candidate in candidates:
            if candidate.track_id == track_id:
                return candidate
        return None


def main(args: Sequence[str] | None = None) -> None:
    """Start the Re-ID node."""
    rclpy.init(args=args)
    node = ReidNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
