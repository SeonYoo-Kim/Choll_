import { defineConfig } from 'orval';

export default defineConfig({
  choll: {
    input: {
      target: './openapi/openapi.yaml',
    },
    output: {
      mode: 'tags-split',
      target: './src/shared/api/generated',
      schemas: './src/shared/api/generated/model',
      client: 'react-query',
      httpClient: 'axios',
      mock: true,
      clean: true,
      formatter: 'prettier',
      override: {
        mutator: {
          path: './src/shared/api/http.ts',
          name: 'http',
        },
      },
    },
  },
});
