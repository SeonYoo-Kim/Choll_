-- SLAM 세계좌표(m) -> FE 평면도(1000x600) 픽셀 아핀, 이미지 정합 기반 초기 근사값 (2026-08-08)
-- 산출: RViz 스크린샷/반전본/평면도 3장 정합 (잔차: 서가 기준 3~62px)
-- 시연 장소에서 scripts/calibrate_map_transform.py 3점 캘리브레이션으로 교체할 것
UPDATE library_maps SET
    affine_a11 = -127.740647802, affine_a12 = -61.889825701,
    affine_a21 = 47.371462021, affine_a22 = -97.774734011,
    affine_tx = 834.804938333, affine_ty = 357.108555490
WHERE id = 2;
