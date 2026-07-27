import { Home, MapPin, PackageOpen, Search } from 'lucide-react';
import { NavLink, Outlet } from 'react-router';

import logo from '@/assets/logo.png';
import { Toast } from '@/shared/ui/toast/Toast';

import styles from './AppLayout.module.scss';

const NAV_ITEMS = [
  { to: '/', label: '홈', Icon: Home },
  { to: '/map', label: '지도', Icon: MapPin },
  { to: '/slots', label: '슬롯 관리', Icon: PackageOpen },
  { to: '/search', label: '도서 검색', Icon: Search },
] as const;

// 설정 페이지 미사용 결정 — 다시 살리려면 Settings2 아이콘 import와 함께 주석 해제
// const MOBILE_NAV_ITEMS = [...NAV_ITEMS, { to: '/settings', label: '설정', Icon: Settings2 }];
const MOBILE_NAV_ITEMS = [...NAV_ITEMS];

/** 공통 레이아웃 — 데스크톱 사이드바 + 모바일 하단 탭 + 페이지 Outlet. */
export function AppLayout() {
  return (
    <main className={styles.page}>
      <section className={styles.frame}>
        <aside className={styles.sidebar}>
          <img src={logo} alt="사서만 쫄래쫄래 로고" className={styles.logo} />
          <div className={styles.nav}>
            {MOBILE_NAV_ITEMS.map(({ to, label, Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `${styles.navItem} ${isActive ? styles.navActive : ''}`
                }
              >
                <Icon size={18} />
                {label}
              </NavLink>
            ))}
          </div>
        </aside>
        <div className={styles.main}>
          <div className={styles.content}>
            <Outlet />
          </div>
        </div>
        <nav className={styles.mobileNav}>
          {MOBILE_NAV_ITEMS.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `${styles.mobileNavItem} ${isActive ? styles.mobileNavActive : ''}`
              }
            >
              <Icon size={20} />
              {label}
            </NavLink>
          ))}
        </nav>
      </section>
      <Toast />
    </main>
  );
}
