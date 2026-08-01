import { expect, test } from '@playwright/test';

// MSW(VITE_ENABLE_MSW=true)로 BE 없이 도는 스모크 테스트

test('홈이 카트 현황과 제어를 렌더링한다', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByText('카트와 함께, 쫄래쫄래')).toBeVisible();
  await expect(page.getByText('카트 정리 현황')).toBeVisible();
  await expect(page.getByText('카트 제어')).toBeVisible();
});

test('슬롯 관리가 MSW 픽스처 슬롯을 렌더링한다', async ({ page }) => {
  await page.goto('/slots');

  await expect(page.getByText('전체 12')).toBeVisible();
  await expect(page.getByText('어린 왕자')).toBeVisible();
  await expect(page.getByText('RFID 인식 불가')).toBeVisible();
});

test('도서 검색으로 책을 찾을 수 있다', async ({ page }) => {
  await page.goto('/search');

  await page.getByPlaceholder('예: 불편한 편의점, 813.7').fill('불편한');
  await expect(page.getByText('불편한 편의점')).toBeVisible();
  await expect(page.getByText('김호연 · 813.7-김95ㅂ')).toBeVisible();
});
