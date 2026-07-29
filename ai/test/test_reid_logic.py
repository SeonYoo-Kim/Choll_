"""Unit tests for Re-ID crop quality and recovery acceptance (no ROS required)."""

import importlib

reid_logic = importlib.import_module("reid_logic")
accept_recovery = reid_logic.accept_recovery
candidate_is_feasible = reid_logic.candidate_is_feasible
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


class TestCandidateIsFeasible:
    def test_same_spot_same_size_is_feasible(self):
        assert candidate_is_feasible(320, 400, 330, 390, elapsed_sec=0.5)

    def test_result14_distant_person_rejected(self):
        # 재현: 1.2m(높이 ~460px) 추적 중 상실 → 1초 뒤 6m 타인(높이 ~110px).
        # 크기 비율 0.24는 1초 허용 범위(0.54~1.85)를 벗어난다.
        assert not candidate_is_feasible(320, 460, 200, 110, elapsed_sec=1.0)

    def test_distant_person_allowed_after_long_absence(self):
        # 오래 사라졌다 돌아온 장기 재등장은 사실상 제한하지 않는다.
        assert candidate_is_feasible(320, 460, 200, 110, elapsed_sec=10.0)

    def test_center_jump_rejected_when_too_fast(self):
        # 0.2초 만에 화면 반대편(500px 이동)은 도달 불가.
        assert not candidate_is_feasible(70, 400, 570, 400, elapsed_sec=0.2)

    def test_center_jump_allowed_given_enough_time(self):
        # 같은 이동도 2초면 300px/s 기준 도달 가능 (60px 여유 포함).
        assert candidate_is_feasible(70, 400, 570, 400, elapsed_sec=2.0)

    def test_size_band_widens_with_time(self):
        # 비율 0.5: 0.2초(허용 0.88~1.14)엔 기각, 2초(허용 0.42~2.4)엔 통과.
        assert not candidate_is_feasible(320, 400, 320, 200, elapsed_sec=0.2)
        assert candidate_is_feasible(320, 400, 320, 200, elapsed_sec=2.0)

    def test_invalid_heights_rejected(self):
        assert not candidate_is_feasible(320, 0, 320, 200, elapsed_sec=1.0)
        assert not candidate_is_feasible(320, 400, 320, 0, elapsed_sec=1.0)

    def test_negative_elapsed_treated_as_zero(self):
        assert candidate_is_feasible(320, 400, 320, 395, elapsed_sec=-1.0)


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
