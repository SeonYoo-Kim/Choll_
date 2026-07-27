import { useState } from 'react';

import { BatteryMedium, Bell } from 'lucide-react';

import styles from './SettingsPage.module.scss';

function SettingSwitch({ enabled, onClick }: { enabled: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={enabled}
      className={`${styles.switch} ${enabled ? styles.switchOn : ''}`}
    >
      <span className={styles.knob} />
    </button>
  );
}

/** 설정 — 카트 상태 확인과 알림 방식 조정. (BE 연동 전 로컬 상태 데모) */
export function SettingsPage() {
  const [arrivalNotice, setArrivalNotice] = useState(true);
  const [soundOn, setSoundOn] = useState(false);

  return (
    <>
      <div className={styles.pageHeader}>
        <p className={styles.overline}>CART PREFERENCES</p>
        <h1 className={styles.pageTitle}>카트 설정</h1>
        <p className={styles.pageDesc}>카트의 이동, 인식, 알림 방식을 조정할 수 있어요.</p>
      </div>
      <div className={styles.grid}>
        <section className={styles.card}>
          <div className={styles.cardHeader}>
            <span className={`${styles.cardIcon} ${styles.mint}`}>
              <BatteryMedium size={20} />
            </span>
            <div>
              <h2 className={styles.cardTitle}>카트 상태</h2>
              <p className={styles.cardDesc}>연결 상태를 확인해요</p>
            </div>
          </div>
          <div className={styles.statGrid}>
            <div className={styles.stat}>
              <strong>82%</strong>
              <span>배터리</span>
            </div>
            <div className={styles.stat}>
              <strong>정상</strong>
              <span>RFID 리더</span>
            </div>
          </div>
        </section>
        <section className={styles.card}>
          <div className={styles.cardHeader}>
            <span className={`${styles.cardIcon} ${styles.red}`}>
              <Bell size={20} />
            </span>
            <div>
              <h2 className={styles.cardTitle}>알림 및 관리</h2>
              <p className={styles.cardDesc}>도착 알림과 카트 상태를 관리해요</p>
            </div>
          </div>
          <div className={styles.switchList}>
            <div className={styles.switchRow}>
              <span>구역 도착 알림</span>
              <SettingSwitch
                enabled={arrivalNotice}
                onClick={() => setArrivalNotice(!arrivalNotice)}
              />
            </div>
            <div className={styles.switchRow}>
              <span>효과음</span>
              <SettingSwitch enabled={soundOn} onClick={() => setSoundOn(!soundOn)} />
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
