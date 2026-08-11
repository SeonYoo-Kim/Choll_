-- SLAM 세계좌표(m) -> FE 평면도(1000x600) 픽셀 아핀 — library_v2 지도 기준 (2026-08-09)
-- v2 = 서가 블록 2개 배치 완료 후 재매핑 + GIMP 정리본 (289x207, res 0.05, origin -8.34,-6.94)
-- 산출: v2 pgm 단독 분석 (벽 프레임 -8도, 서가 박스 2개·사서 테이블 노치로 방향 확정)
--   검증 잔차: 서가 블록 19~25cm (평면도 도식화 수준), 사서 테이블 노치 영역 일치
-- ⚠️ 이전 library-map-affine-initial.sql(v1 지도 기준)은 v2와 좌표계가 달라 폐기 —
--   v1 아핀을 v2 좌표에 쓰면 200~650px·약 59도 어긋난다
-- 시연장에서 scripts/calibrate_map_transform.py 3점 캘리브레이션으로 다듬을 것
UPDATE library_maps SET
    affine_a11 = -20.317241000, affine_a12 = 144.564682000,
    affine_a21 = 108.029244000, affine_a22 = 15.182520000,
    affine_tx = 917.881000000, affine_ty = 175.555000000
WHERE id = 2;
