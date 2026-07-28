/**
 * 카트 실시간 이벤트 WebSocket 클라이언트.
 *
 * 계약(frontend/CLAUDE.md · API 명세서):
 * - 엔드포인트: /ws/carts/{cartId}
 * - BE → FE 단방향 JSON 이벤트 13종 (CART_POSITION_UPDATE, SLOT_UPDATED, FOLLOW_TARGETS_UPDATED 등)
 * - 재연결 시 REST 재조회로 상태 복구 (BE-WS-03) → onReconnect 콜백에서 query invalidate 수행
 */

/** API 명세서에 정의된 이벤트 타입. 명세 확정 시 13종 전체를 채운다. */
export type CartWsEventType =
  | 'CART_POSITION_UPDATE'
  | 'CART_ARRIVED'
  | 'SLOT_UPDATED'
  | 'FOLLOW_TARGETS_UPDATED'
  // TODO: API 명세서의 나머지 이벤트 타입 추가
  | (string & {});

/**
 * CART_POSITION_UPDATE 페이로드 초안.
 * position은 SLAM 좌표(m) — FE에서 MapInfo(resolution/origin)로 이미지 %로 변환한다.
 * TODO: 노션 API 명세서 확정 시 필드명·단위를 동기화할 것 (FE 단독 확정 금지).
 */
export interface CartPositionUpdatePayload {
  position: { x: number; y: number; yaw?: number };
  /** 현재 구역 shelf_zone.id (구역 밖이면 null) */
  zoneId: number | null;
  zoneName?: string;
}

/** CART_ARRIVED(목적지 도착) 페이로드 초안. TODO: 노션 명세 확정 시 동기화. */
export interface CartArrivedPayload {
  zoneId: number;
  zoneName?: string;
}

export interface CartWsEvent<TPayload = unknown> {
  type: CartWsEventType;
  payload: TPayload;
}

type EventHandler = (event: CartWsEvent) => void;

interface CartSocketOptions {
  /** 기본값: `ws://<현재 호스트>` (VITE_WS_URL로 오버라이드) */
  baseUrl?: string;
  /** 재연결 성공 시 호출 — REST 재조회로 상태 복구용 */
  onReconnect?: () => void;
  maxRetryDelayMs?: number;
}

const INITIAL_RETRY_DELAY_MS = 1_000;
const DEFAULT_MAX_RETRY_DELAY_MS = 15_000;

/**
 * 지수 백오프 재연결을 내장한 카트 WebSocket 래퍼.
 * 사용처(카트 관리 화면)에서 mount 시 connect, unmount 시 close를 호출한다.
 */
export class CartSocket {
  private socket: WebSocket | null = null;
  private handlers = new Map<CartWsEventType, Set<EventHandler>>();
  private retryDelayMs = INITIAL_RETRY_DELAY_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUser = false;
  private hasConnectedOnce = false;
  private readonly cartId: string;
  private readonly options: CartSocketOptions;

  constructor(cartId: string, options: CartSocketOptions = {}) {
    this.cartId = cartId;
    this.options = options;
  }

  connect(): void {
    this.closedByUser = false;
    const base =
      this.options.baseUrl ||
      import.meta.env.VITE_WS_URL ||
      `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
    const socket = new WebSocket(`${base}/ws/carts/${this.cartId}`);
    this.socket = socket;

    socket.onopen = () => {
      if (this.hasConnectedOnce) {
        this.options.onReconnect?.();
      }
      this.hasConnectedOnce = true;
      this.retryDelayMs = INITIAL_RETRY_DELAY_MS;
    };

    socket.onmessage = (message: MessageEvent<string>) => {
      try {
        const event = JSON.parse(message.data) as CartWsEvent;
        this.handlers.get(event.type)?.forEach((handler) => handler(event));
      } catch (error) {
        console.error('[CartSocket] 이벤트 파싱 실패:', error, message.data);
      }
    };

    socket.onclose = () => {
      if (this.closedByUser) {
        return;
      }
      this.reconnectTimer = setTimeout(() => this.connect(), this.retryDelayMs);
      this.retryDelayMs = Math.min(
        this.retryDelayMs * 2,
        this.options.maxRetryDelayMs ?? DEFAULT_MAX_RETRY_DELAY_MS,
      );
    };
  }

  /** 이벤트 구독. 반환된 함수를 호출하면 구독 해제된다. */
  on<TPayload>(type: CartWsEventType, handler: (event: CartWsEvent<TPayload>) => void): () => void {
    const set = this.handlers.get(type) ?? new Set();
    set.add(handler as EventHandler);
    this.handlers.set(type, set);
    return () => {
      set.delete(handler as EventHandler);
    };
  }

  close(): void {
    this.closedByUser = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
  }
}
