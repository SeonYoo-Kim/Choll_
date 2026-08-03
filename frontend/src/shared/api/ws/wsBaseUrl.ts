/**
 * WebSocket 기본 주소 — `ws://<현재 호스트>` (VITE_WS_URL로 오버라이드).
 * 이벤트 채널(CartSocket)과 영상 채널(useCartVideo)이 같은 규칙을 쓰도록 한곳에 둔다.
 */
export function wsBaseUrl(override?: string): string {
  return (
    override ||
    import.meta.env.VITE_WS_URL ||
    `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
  );
}
