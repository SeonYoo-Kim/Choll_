/**
 * 카트 실시간 이벤트 WebSocket 클라이언트.
 *
 * 계약(frontend/CLAUDE.md · API 명세서):
 * - 엔드포인트: /ws/carts/{cartId}
 * - BE → FE 단방향 JSON 이벤트 13종 (CART_POSITION_UPDATE, SLOT_UPDATED, FOLLOW_TARGETS_UPDATED 등)
 * - 재연결 시 REST 재조회로 상태 복구 (BE-WS-03) → onReconnect 콜백에서 query invalidate 수행
 */

import { wsBaseUrl } from './wsBaseUrl';

import type { Slot, TaskProgress } from '@/shared/api/generated/model';

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
  | 'ALERT_RESOLVED' // WS-FE-13 실시간 경고 해제
  | 'TRACKS_UPDATED'; // AI 사람 탐지 박스 갱신 — 명세의 WS-FE-08 자리를 BE가 이 이름으로 구현했다

/**
 * WS-FE-01 CART_POSITION_UPDATE 페이로드.
 * x·y는 지도 이미지의 좌상단을 원점으로 하는 픽셀 좌표다.
 */
export interface CartPositionUpdatePayload {
  mapId: number;
  x: number;
  y: number;
  /** 방향각 (라디안) */
  yaw: number;
  /** 위치 유효 여부 — false면 SLAM 위치 신뢰 불가 */
  valid: boolean;
}

/**
 * WS-FE-03 CART_CONNECTION_UPDATED 페이로드.
 *
 * BE는 **상태가 바뀌는 순간에만** 보낸다 (하트비트 수신 → ONLINE,
 * `cart.connection.offline-timeout-seconds`(기본 15초) 무신호 → OFFLINE).
 * 이미 끊긴 상태로 화면에 들어오면 이벤트가 오지 않으므로, 진입 시점 상태는
 * REST CART-01(`CartDetail.online`)로 따로 채워야 한다.
 *
 * lastSeenAt은 마지막 통신 시각 — BE가 LocalDateTime(Asia/Seoul)을 보내므로
 * 타임존 표기가 없는 ISO 문자열이다.
 */
export interface CartConnectionUpdatedPayload {
  online: boolean;
  lastSeenAt: string | null;
}

/**
 * WS-FE-04 SLOT_UPDATED 페이로드 — REST GET /slots 항목(Slot)과 동일하다.
 * BE가 같은 DTO(SlotService.Response)를 REST와 WS 양쪽에 쓴다 (BE 확인: 2026-07-30).
 */
export type SlotUpdatedPayload = Slot;

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
  'ACCEPTED' | 'STARTED' | 'STOPPED' | 'ARRIVED' | 'CANCELLED' | 'FAILED';

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

/** WS-FE-07의 추종 상태. 시작·일시정지·종료. TODO: 값 이름 BE 확정 필요 */
export type FollowStatus = 'STARTED' | 'PAUSED' | 'STOPPED';

/**
 * WS-FE-07 FOLLOW_STATUS_UPDATED 페이로드.
 * TODO: 필드명 BE 확정 필요.
 */
export interface FollowStatusUpdatedPayload {
  status: FollowStatus;
}

/**
 * AI가 탐지한 사람 하나. x·y는 bbox 좌상단, w·h는 크기이며
 * 모두 원본 영상 해상도(TracksUpdatedPayload.image_*) 기준 픽셀이다.
 */
export interface Track {
  /** ByteTrack이 부여한 track id — 추종 대상 선택 시 이 값을 BE로 보낸다 */
  id: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * TRACKS_UPDATED 페이로드 — 영상 프레임 위에 그릴 사람 박스 목록.
 * snake_case인 이유: AI(Python) → BE를 거쳐 그대로 내려오는 필드명이다.
 * 화면 크기와 무관하게 항상 image_width·image_height 기준으로 비례 변환해서 써야 한다.
 */
export interface TracksUpdatedPayload {
  image_width: number;
  image_height: number;
  tracks: Track[];
}

export interface CartWsEvent<TPayload = unknown> {
  type: CartWsEventType;
  payload: TPayload;
}

/**
 * WS-FE-10 TASK_PROGRESS_UPDATED 페이로드 — REST GET /tasks/progress(TaskProgress)와 동일하다.
 * BE가 같은 DTO(TaskService.ProgressResponse)를 REST와 WS 양쪽에 쓴다.
 */
export type TaskProgressUpdatedPayload = TaskProgress;

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
    // 이미 살아있는 연결이 있으면 그대로 사용 (StrictMode 이중 실행 등 중복 connect 방지)
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    const base = wsBaseUrl(this.options.baseUrl);
    const socket = new WebSocket(`${base}/ws/carts/${this.cartId}`);
    this.socket = socket;

    // 각 핸들러는 자신이 현재 소켓일 때만 동작한다 — close() 후 뒤늦게 도착하는
    // 낡은 소켓의 이벤트(특히 onclose)가 재연결을 일으켜 연결이 2개가 되는 것을 방지
    socket.onopen = () => {
      if (this.socket !== socket) return;
      console.info(`[CartSocket] 연결됨: ${base}/ws/carts/${this.cartId}`);
      if (this.hasConnectedOnce) {
        this.options.onReconnect?.();
      }
      this.hasConnectedOnce = true;
      this.retryDelayMs = INITIAL_RETRY_DELAY_MS;
    };

    socket.onmessage = (message: MessageEvent<string>) => {
      if (this.socket !== socket) return;
      try {
        const event = JSON.parse(message.data) as CartWsEvent;
        console.info('[CartSocket] 수신:', event.type, event.payload);
        this.handlers.get(event.type)?.forEach((handler) => handler(event));
      } catch (error) {
        console.error('[CartSocket] 이벤트 파싱 실패:', error, message.data);
      }
    };

    socket.onclose = () => {
      if (this.socket !== socket) return;
      if (this.closedByUser) {
        return;
      }
      console.info(`[CartSocket] 연결 끊김 — ${this.retryDelayMs}ms 후 재연결 시도`);
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
    if (this.socket) {
      console.info('[CartSocket] 연결 종료');
      this.socket.close();
      this.socket = null;
    }
  }
}
