"""Unit tests for the FE target-selection bridge logic (no ROS required)."""

import importlib

fe_bridge_logic = importlib.import_module("fe_bridge_logic")
RateLimiter = fe_bridge_logic.RateLimiter
build_tracks_payload = fe_bridge_logic.build_tracks_payload
parse_select_command = fe_bridge_logic.parse_select_command


class TestRateLimiter:
    def test_first_frame_always_sends(self):
        limiter = RateLimiter(min_interval_sec=0.1)
        assert limiter.should_send(10.0)

    def test_frames_within_interval_are_dropped(self):
        # 10fps 제한: 0.1초 안에 들어온 프레임은 버린다 (drop-oldest)
        limiter = RateLimiter(min_interval_sec=0.1)
        limiter.should_send(10.0)
        assert not limiter.should_send(10.05)
        assert limiter.should_send(10.11)

    def test_zero_interval_never_drops(self):
        limiter = RateLimiter(min_interval_sec=0.0)
        assert limiter.should_send(1.0)
        assert limiter.should_send(1.0)


class TestBuildTracksPayload:
    def test_converts_center_to_top_left(self):
        # bbox 중심 (320,240) 크기 180x420 → 좌상단 (230, 30)
        payload = build_tracks_payload(640, 480, [(16, 320.0, 240.0, 180.0, 420.0)])
        assert payload["image_width"] == 640
        assert payload["image_height"] == 480
        assert payload["tracks"] == [
            {"id": 16, "x": 230, "y": 30, "w": 180, "h": 420}
        ]

    def test_empty_tracks_is_valid_payload(self):
        # 검출 없음도 유효한 상태 — FE가 박스를 지울 근거가 된다
        payload = build_tracks_payload(640, 480, [])
        assert payload["tracks"] == []

    def test_values_are_ints(self):
        payload = build_tracks_payload(640, 480, [(3, 100.7, 50.2, 33.3, 66.6)])
        track = payload["tracks"][0]
        assert all(isinstance(value, int) for value in track.values())


class TestParseSelectCommand:
    def test_select_target_returns_track_id(self):
        payload = '{"command":"SELECT_TARGET","trackId":16}'
        assert parse_select_command(payload) == 16

    def test_other_commands_ignored(self):
        # choll/cart/cmd에는 MOVE/CANCEL도 흐른다 — 브릿지는 SELECT_TARGET만 처리
        payload = '{"requestId":1,"command":"MOVE","zoneId":8,"x":775.0,"y":505.0}'
        assert parse_select_command(payload) is None

    def test_missing_track_id_ignored(self):
        assert parse_select_command('{"command":"SELECT_TARGET"}') is None

    def test_non_integer_track_id_ignored(self):
        as_string = '{"command":"SELECT_TARGET","trackId":"16"}'
        as_bool = '{"command":"SELECT_TARGET","trackId":true}'
        assert parse_select_command(as_string) is None
        assert parse_select_command(as_bool) is None

    def test_malformed_json_ignored(self):
        assert parse_select_command("not-json") is None
        assert parse_select_command("[1,2,3]") is None
