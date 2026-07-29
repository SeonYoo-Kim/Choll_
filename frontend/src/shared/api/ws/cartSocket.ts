/**
 * 카트 실시간 이벤트 WebSocket 클라이언트.
 *
 * 계약(frontend/CLAUDE.md · API 명세서):
 * - 엔드포인트: /ws/carts/{cartId}
 * - BE → FE 단방향 JSON 이벤트 13종 (CART_POSITION_UPDATE, SLOT_UPDATED, FOLLOW_TARGETS_UPDATED 등)
 * - 재연결 시 REST 재조회로 상태 복구 (BE-WS-03) → onReconnect 콜백에서 query invalidate 수행
 */

/** API 명세서(노션 WS-FE-01~13)에 정의된 이벤트 타입 13종. */
export type CartWsEventType =
  | 'CART_POSITION_UPDATE' // WS-FE-01 카트 위치 변경
  | 'CART_STATUS_UPDATED' // WS-FE-02 카트 동작 상태 변경
  | 'CART_CONNECTION_UPDATED' // WS-FE-03 카트 연결 상태 변경
  | 'SLOT_UPDATED' // WS-FE-04 슬롯 상태 변경
  | 'CURRENT_ZONE_UPDATED' // WS-FE-05 현재 구역 진입/이탈
  | 'NAVIGATION_STATUS_UPDATED' // WS-FE-06 목적지 이동 상태 변경
  | 'FOLLOW_STATUS_UPDATED' // WS-FE-07 사서 추종 상태 변경
  | 'FOLLOW_TARGETS_UPDATED' // WS-FE-08 추종 대상 후보 변경
  | 'CURRENT_ZONE_TASKS_UPDATED' // WS-FE-09 현재 구역 정리 대상 변경
  | 'TASK_PROGRESS_UPDATED' // WS-FE-10 정리 진행률 변경
  | 'RFID_RESCAN_COMPLETED' // WS-FE-11 RFID 재인식 결과
  | 'ALERT_OCCURRED' // WS-FE-12 실시간 경고 발생
  | 'ALERT_RESOLVED'; // WS-FE-13 실시간 경고 해제

/**
 * WS-FE-01 CART_POSITION_UPDATE 페이로드.
 * 명세 데이터: 지도 ID, X·Y 표시 좌표, 방향, 위치 유효 여부.
 * x·y는 지도 이미지 픽셀 기준 표시 좌표로 해석한다.
 * TODO: 필드명·좌표 단위는 BE 구현 시 확정 필요 (FE 단독 확정 금지).
 */
export interface CartPositionUpdatePayload {
  mapId: number;
  x: number;
  y: number;
  /** 방향각 (라디안) */
  yaw?: number;
  /** 위치 유효 여부 — false면 SLAM 위치 신뢰 불가 */
  valid: boolean;
}

/**
 * WS-FE-05 CURRENT_ZONE_UPDATED 페이로드. 명세 데이터: 이전 구역, 현재 구역.
 * 구역 밖(통로 등)이면 null. TODO: 필드명 BE 확정 필요.
 */
export interface CurrentZoneUpdatedPayload {
  previousZoneId: number | null;
  currentZoneId: number | null;
}

/** WS-FE-06의 이동 상태. 명세 발생 조건: 접수·시작·정지·도착·취소·실패 */
export type NavigationStatus =
  | 'ACCEPTED'
  | 'STARTED'
  | 'STOPPED'
  | 'ARRIVED'
  | 'CANCELLED'
  | 'FAILED';

/**
 * WS-FE-06 NAVIGATION_STATUS_UPDATED 페이로드.
 * 명세 데이터: 이동 ID, 이동 상태, 목적지, 실패 사유. TODO: 필드명 BE 확정 필요.
 */
export interface NavigationStatusUpdatedPayload {
  navigationId?: number;
  status: NavigationStatus;
  /** 목적지 구역 shelf_zone.id */
  destinationZoneId?: number;
  failReason?: string;
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
        console.log('[CartSocket] 위치 이벤트 수신:', event.payload);
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
