import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5174',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // 개발 서버(5173)와 분리된 전용 포트에서 MSW를 강제해, .env.development.local의
    // 실서버 모드 설정이 E2E를 오염시키지 않게 한다 (스모크 테스트는 모킹 전제)
    command: 'pnpm dev --port 5174 --strictPort',
    url: 'http://localhost:5174',
    reuseExistingServer: !process.env.CI,
    env: { VITE_ENABLE_MSW: 'true' },
  },
});
