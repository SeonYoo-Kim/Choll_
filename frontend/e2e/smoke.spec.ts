import { expect, test } from '@playwright/test';

// MSW(VITE_ENABLE_MSW=true)로 BE 없이 도는 스모크 테스트
test('대시보드가 슬롯 보드를 렌더링한다', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('슬롯 상태 보드')).toBeVisible();
  // MSW 픽스처의 슬롯 1 카드가 보여야 한다
  await expect(page.getByText('슬롯 1')).toBeVisible();
  await expect(page.getByText('어린 왕자')).toBeVisible();
});
