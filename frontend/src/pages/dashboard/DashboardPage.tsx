import { Alert, Col, Layout, Row, Spin, Typography } from 'antd';

import { SlotCard } from '@/features/slot-board/ui/SlotCard';
import { useListSlots } from '@/shared/api/generated/slots/slots';

import styles from './DashboardPage.module.scss';

/** 데모용 고정 카트 ID — 카트 선택 화면이 생기면 라우트 파라미터로 대체 */
const DEMO_CART_ID = 'cart-001';

/** 슬롯 상태 보드를 보여주는 메인 대시보드. */
export function DashboardPage() {
  const { data: slots, isPending, isError } = useListSlots(DEMO_CART_ID);

  return (
    <Layout className={styles.layout}>
      <Layout.Header className={styles.header}>
        <Typography.Title level={4} className={styles.title}>
          Choll — 사서용 카트 관리
        </Typography.Title>
      </Layout.Header>
      <Layout.Content className={styles.content}>
        <Typography.Title level={5}>슬롯 상태 보드</Typography.Title>
        {isPending && <Spin />}
        {isError && (
          <Alert
            type="error"
            message="슬롯 정보를 불러오지 못했습니다"
            description="네트워크 상태를 확인한 뒤 새로고침해 주세요."
          />
        )}
        <Row gutter={[16, 16]}>
          {slots?.map((slot) => (
            <Col key={slot.slotNo} xs={24} sm={12} md={8} lg={6}>
              <SlotCard slot={slot} />
            </Col>
          ))}
        </Row>
      </Layout.Content>
    </Layout>
  );
}
