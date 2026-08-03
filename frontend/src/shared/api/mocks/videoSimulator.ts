import { ws } from 'msw';

import { broadcastTracks } from './cartSimulator';

/**
 * 개발용 카트 카메라 시뮬레이터 (가짜 BE).
 *
 * 실제 BE 계약 그대로 두 채널을 흉내 낸다:
 * - 영상: /ws/carts/{cartId}/video 로 바이너리 1메시지 = JPEG 1프레임
 * - 박스: 이벤트 채널(/ws/carts/{cartId})의 TRACKS_UPDATED
 *
 * 그림과 박스를 같은 루프에서 만들기 때문에 좌표가 항상 일치한다 —
 * 박스를 눌렀을 때 실제로 그 사람이 선택되는지 확인할 수 있다.
 */

const FRAME_WIDTH = 640;
const FRAME_HEIGHT = 480;
const FPS = 10;
const FRAME_INTERVAL_MS = 1000 / FPS;

// 주의: cartSimulator의 이벤트 채널 패턴(*/ws/carts/:cartId)과 겹치지 않게 /video까지 명시한다
const videoWsLink = ws.link('*/ws/carts/:cartId/video');

interface SimulatedPerson {
  /** ByteTrack track id 흉내 — 화면 박스 라벨과 선택 요청에 쓰인다 */
  id: number;
  /** 발밑 중심 x (px) */
  centerX: number;
  /** 발밑 y (px) */
  footY: number;
  /** 머리끝~발밑 높이 (px) */
  height: number;
  /** 프레임당 x 이동량 (px) */
  velocityX: number;
  color: string;
}

const people: SimulatedPerson[] = [
  { id: 3, centerX: 190, footY: 430, height: 300, velocityX: 2.2, color: '#e8b04b' },
  { id: 7, centerX: 470, footY: 396, height: 232, velocityX: -1.5, color: '#7fb2e5' },
];

/** 사람의 bbox — 몸 너비는 키에 비례한다고 본다 */
function boundingBox(person: SimulatedPerson) {
  const w = person.height * 0.42;
  return {
    id: person.id,
    x: Math.round(person.centerX - w / 2),
    y: Math.round(person.footY - person.height),
    w: Math.round(w),
    h: person.height,
  };
}

function step(person: SimulatedPerson): void {
  const halfWidth = (person.height * 0.42) / 2;
  person.centerX += person.velocityX;
  if (person.centerX - halfWidth < 0 || person.centerX + halfWidth > FRAME_WIDTH) {
    person.velocityX *= -1;
    person.centerX += person.velocityX;
  }
}

let canvas: HTMLCanvasElement | null = null;

function getContext(): CanvasRenderingContext2D | null {
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.width = FRAME_WIDTH;
    canvas.height = FRAME_HEIGHT;
  }
  return canvas.getContext('2d');
}

/** 도서관처럼 보이는 배경 — 서가 몇 개와 바닥 */
function drawBackground(ctx: CanvasRenderingContext2D): void {
  ctx.fillStyle = '#2b2722';
  ctx.fillRect(0, 0, FRAME_WIDTH, FRAME_HEIGHT);

  ctx.fillStyle = '#3a332b';
  ctx.fillRect(0, 360, FRAME_WIDTH, FRAME_HEIGHT - 360);

  // 서가 3개
  for (let i = 0; i < 3; i += 1) {
    const x = 40 + i * 210;
    ctx.fillStyle = '#4a3f33';
    ctx.fillRect(x, 90, 150, 270);
    ctx.fillStyle = '#5d5044';
    for (let shelf = 0; shelf < 4; shelf += 1) {
      ctx.fillRect(x + 6, 100 + shelf * 66, 138, 8);
    }
  }
}

function drawPerson(ctx: CanvasRenderingContext2D, person: SimulatedPerson): void {
  const box = boundingBox(person);
  const headRadius = box.w * 0.26;
  const headCenterY = box.y + headRadius;

  ctx.fillStyle = person.color;
  // 몸통 — 머리 아래부터 발밑까지
  ctx.beginPath();
  ctx.roundRect(
    box.x + box.w * 0.18,
    headCenterY + headRadius * 0.6,
    box.w * 0.64,
    box.h * 0.74,
    14,
  );
  ctx.fill();
  // 머리
  ctx.beginPath();
  ctx.arc(box.x + box.w / 2, headCenterY, headRadius, 0, Math.PI * 2);
  ctx.fill();
}

let frameCount = 0;

function renderFrame(): void {
  const ctx = getContext();
  if (!ctx) return;

  people.forEach(step);
  drawBackground(ctx);
  people.forEach((person) => drawPerson(ctx, person));

  // 프레임이 실제로 흐르는지 눈으로 확인할 수 있게 카운터를 찍는다
  frameCount += 1;
  ctx.fillStyle = 'rgba(255, 255, 255, 0.55)';
  ctx.font = '14px monospace';
  ctx.fillText(`MOCK CAM  frame ${frameCount}`, 12, 24);

  broadcastTracks({
    image_width: FRAME_WIDTH,
    image_height: FRAME_HEIGHT,
    tracks: people.map(boundingBox),
  });

  canvas?.toBlob(
    (blob) => {
      if (!blob) return;
      void blob.arrayBuffer().then((buffer) => videoWsLink.broadcast(buffer));
    },
    'image/jpeg',
    0.7,
  );
}

let frameTimer: ReturnType<typeof setInterval> | null = null;
let viewerCount = 0;

function startStreaming(): void {
  if (frameTimer !== null) return;
  console.info('[MockCam] 영상 송출 시작');
  frameTimer = setInterval(renderFrame, FRAME_INTERVAL_MS);
}

function stopStreaming(): void {
  if (frameTimer === null) return;
  console.info('[MockCam] 영상 송출 중지 (시청자 없음)');
  clearInterval(frameTimer);
  frameTimer = null;
}

/** 영상 WS 모킹 핸들러 — 보는 사람이 있을 때만 프레임을 만든다 */
export const cartVideoWsHandler = videoWsLink.addEventListener('connection', ({ client }) => {
  viewerCount += 1;
  startStreaming();
  client.addEventListener('close', () => {
    viewerCount = Math.max(0, viewerCount - 1);
    if (viewerCount === 0) {
      stopStreaming();
    }
  });
});
