import axios from 'axios';
import type { AxiosRequestConfig } from 'axios';

/**
 * 공용 axios 인스턴스.
 * baseURL을 비워두면 same-origin(/api/...)으로 요청하며,
 * 개발 중에는 vite dev proxy 또는 MSW가 이를 처리한다.
 */
export const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 10_000,
});

/**
 * orval mutator. 생성된 모든 API 클라이언트가 이 함수를 통해 요청한다.
 * 인증 헤더, 공통 에러 처리 등은 여기(또는 axiosInstance 인터셉터)에 추가한다.
 */
export const http = <T>(config: AxiosRequestConfig): Promise<T> =>
  axiosInstance.request<T>(config).then((response) => response.data);
