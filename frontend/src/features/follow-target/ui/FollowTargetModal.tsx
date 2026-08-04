import { useEffect, useRef } from 'react';

import { Loader2, X } from 'lucide-react';

import { isTargetCommandSent, useSelectFollowTarget } from '../api/followTarget';
import { useCartVideo } from '../model/useCartVideo';
import { useTracks } from '../model/useTracks';

import { useToastStore } from '@/shared/ui/toast/toastStore';

import styles from './FollowTargetModal.module.scss';

interface FollowTargetModalProps {
  cartId: number;
  onClose: () => void;
  /** 대상 선택(202)이 성공했을 때 — 부모가 추종 시작 등 후속 처리를 한다 */
  onSelected: (trackId: number) => void;
}

/**
 * 추종 대상 선택 모달 — 카트 카메라 영상 위에 AI가 탐지한 사람 박스를 겹쳐 보여주고,
 * 사서가 박스를 누르면 그 track id를 추종 대상으로 지정한다.
 *
 * 박스를 canvas가 아닌 button 엘리먼트로 그리는 이유:
 * 좌표를 %로 두면 화면 크기가 변해도 영상과 자동으로 맞고, 히트 테스트를 직접 짤 필요가 없으며,
 * 키보드 포커스·hover 같은 것을 브라우저가 알아서 처리한다.
 */
export function FollowTargetModal({ cartId, onClose, onSelected }: FollowTargetModalProps) {
  const frameRef = useRef<HTMLImageElement>(null);
  const videoStatus = useCartVideo(cartId, frameRef);
  const { tracks, imageWidth, imageHeight, received } = useTracks();
  const notify = useToastStore((state) => state.show);

  const selectTarget = useSelectFollowTarget({
    mutation: {
      onSuccess: (response, { data }) => {
        // HTTP 202라도 본문의 status가 "보냄"이 아니면 카트가 대상을 받지 못한 것이다.
        // 여기서 멈추지 않으면 거절당한 채로 추종 시작(FOLLOW-04)까지 진행된다.
        if (!isTargetCommandSent(response)) {
          notify('카트가 추종 대상을 받지 못했어요. 다시 선택해주세요');
          return;
        }
        // 서버가 대상을 정정해 줄 수 있으므로 응답의 trackId를 우선한다
        onSelected(response?.trackId ?? data.trackId);
      },
      onError: () => notify('추종 대상 지정에 실패했어요'),
    },
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  // 영상은 붙었는데 박스가 없는 상태와, 아직 영상도 못 붙은 상태를 구분해서 안내한다
  const hint =
    videoStatus === 'streaming'
      ? received && tracks.length === 0
        ? '카메라에 잡히는 사람이 없어요'
        : !received
          ? '사람을 찾는 중이에요…'
          : null
      : videoStatus === 'connecting'
        ? '카메라를 연결하는 중이에요…'
        : '카메라 연결이 끊겼어요 — 다시 연결하는 중이에요';

  return (
    <div
      className={styles.backdrop}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="follow-target-title"
      >
        <div className={styles.header}>
          <div>
            <span className={styles.overline}>FOLLOW TARGET</span>
            <h3 className={styles.title} id="follow-target-title">
              따라갈 사람을 골라주세요
            </h3>
          </div>
          <button className={styles.close} onClick={onClose} aria-label="닫기">
            <X size={16} />
          </button>
        </div>

        <p className={styles.desc}>영상 속 사람을 누르면 카트가 그 사람을 따라가요.</p>

        <div className={styles.stage} style={{ aspectRatio: `${imageWidth} / ${imageHeight}` }}>
          {/* 프레임은 useCartVideo가 src를 직접 갱신한다 (10 FPS 리렌더 방지) */}
          <img ref={frameRef} className={styles.frame} alt="" />
          {tracks.map((track) => {
            const pending =
              selectTarget.isPending && selectTarget.variables?.data.trackId === track.id;
            return (
              <button
                key={track.id}
                className={`${styles.box} ${pending ? styles.boxPending : ''}`}
                style={{
                  left: `${(track.x / imageWidth) * 100}%`,
                  top: `${(track.y / imageHeight) * 100}%`,
                  width: `${(track.w / imageWidth) * 100}%`,
                  height: `${(track.h / imageHeight) * 100}%`,
                }}
                disabled={selectTarget.isPending}
                onClick={() => selectTarget.mutate({ cartId, data: { trackId: track.id } })}
                aria-label={`${track.id}번 사람을 추종 대상으로 선택`}
              >
                <span className={styles.boxLabel}>
                  {pending && <Loader2 size={12} className={styles.spinner} />}
                  ID {track.id}
                </span>
              </button>
            );
          })}
          {hint && (
            <div className={styles.hint}>
              <Loader2 size={18} className={styles.spinner} />
              {hint}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
