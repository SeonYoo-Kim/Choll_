"""Unit tests for Re-ID crop quality and recovery acceptance (no ROS required)."""

import importlib

reid_logic = importlib.import_module("reid_logic")
accept_recovery = reid_logic.accept_recovery
crop_quality_ok = reid_logic.crop_quality_ok

W, H = 640.0, 480.0  # 실카메라 해상도


class TestCropQualityOk:
    def test_centered_full_body_passes(self):
        assert crop_quality_ok(320, 240, 150, 400, W, H)

    def test_left_clipped_box_rejected(self):
        # 왼쪽 프레임 밖으로 나가는 중인 사람 (center 60, half 폭 80 → x1<0)
        assert not crop_quality_ok(60, 240, 160, 400, W, H)

    def test_right_clipped_box_rejected(self):
        assert not crop_quality_ok(600, 240, 160, 400, W, H)

    def test_top_bottom_touching_is_allowed(self):
        # 1m 추종 거리에서는 전신이 세로 화각을 넘는 게 정상 — 상하 접촉 허용.
        assert crop_quality_ok(320, 240, 200, 480, W, H)

    def test_close_up_torso_rejected(self):
        # result10.mp4 재현: 화면 절반 이상을 덮는 초근접 몸통 조각.
        assert not crop_quality_ok(320, 240, 400, 460, W, H)

    def test_zero_size_rejected(self):
        assert not crop_quality_ok(320, 240, 0, 0, W, H)


class TestAcceptRecovery:
    def test_clear_winner_above_threshold_accepted(self):
        scores = [(5, 0.90), (7, 0.60)]
        assert accept_recovery(scores, similarity_threshold=0.85) == 5

    def test_below_threshold_rejected(self):
        scores = [(5, 0.80), (7, 0.60)]
        assert accept_recovery(scores, similarity_threshold=0.85) is None

    def test_ambiguous_runner_up_within_margin_rejected(self):
        # 비슷한 옷의 두 사람이 둘 다 높은 점수 → 오인 방지 위해 보류.
        scores = [(5, 0.90), (7, 0.88)]
        assert accept_recovery(scores, 0.85, margin=0.05) is None

    def test_single_candidate_needs_no_margin(self):
        assert accept_recovery([(5, 0.86)], 0.85, margin=0.05) == 5

    def test_order_independent(self):
        scores = [(7, 0.60), (5, 0.92)]
        assert accept_recovery(scores, 0.85, margin=0.05) == 5

    def test_empty_scores_rejected(self):
        assert accept_recovery([], 0.85) is None
