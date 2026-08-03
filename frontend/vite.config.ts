/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  // BE 오리진. 다른 PC의 BE(브로커·Jetson이 붙어 있는 쪽)를 볼 때만
  // .env.development.local에 VITE_BE_ORIGIN=http://<BE_PC_IP>:8080 을 넣는다.
  // 브라우저는 항상 dev 서버(same-origin)와만 통신하므로 CORS 설정이 필요 없고,
  // WS 핸드셰이크의 Origin도 http://localhost:5173으로 유지된다.
  const beOrigin = env.VITE_BE_ORIGIN || 'http://localhost:8080';

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      proxy: {
        // 로컬/원격 BE(Spring Boot) 연동 시 사용. MSW 모킹 중에는 워커가 먼저 가로챈다.
        '/api': { target: beOrigin, changeOrigin: true },
        '/ws': { target: beOrigin.replace(/^http/, 'ws'), ws: true },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
      css: true,
    },
  };
});
