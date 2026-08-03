import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { useCartConnectionStore } from '../model/cartConnectionStore';

import { CartOfflineModal } from './CartOfflineModal';

beforeEach(() => {
  useCartConnectionStore.setState({ online: true, lastSeenAt: null, dismissed: false });
});

describe('CartOfflineModal', () => {
  it('연결되어 있으면 아무것도 그리지 않는다', () => {
    const { container } = render(<CartOfflineModal />);
    expect(container).toBeEmptyDOMElement();
  });

  it('끊기면 팝업을 띄운다', () => {
    useCartConnectionStore.setState({ online: false });
    render(<CartOfflineModal />);
    expect(screen.getByText('카트와 연결이 끊겼어요')).toBeInTheDocument();
  });

  it('마지막 통신 시각을 시:분으로 보여준다', () => {
    useCartConnectionStore.setState({ online: false, lastSeenAt: '2026-08-03T21:12:33' });
    render(<CartOfflineModal />);
    expect(screen.getByText(/마지막 통신 오후 9:12/)).toBeInTheDocument();
  });

  it('시각이 없거나 이상하면 그 줄만 뺀다', () => {
    useCartConnectionStore.setState({ online: false, lastSeenAt: '알 수 없음' });
    render(<CartOfflineModal />);
    expect(screen.getByText('카트와 연결이 끊겼어요')).toBeInTheDocument();
    expect(screen.queryByText(/마지막 통신/)).not.toBeInTheDocument();
  });

  it('확인을 누르면 닫히고, 연결이 끊긴 동안에는 다시 뜨지 않는다', async () => {
    useCartConnectionStore.setState({ online: false });
    const { container } = render(<CartOfflineModal />);

    await userEvent.click(screen.getByRole('button', { name: '확인' }));

    expect(container).toBeEmptyDOMElement();
    expect(useCartConnectionStore.getState().dismissed).toBe(true);
  });

  it('연결이 돌아오면 저절로 사라진다', () => {
    useCartConnectionStore.setState({ online: false });
    const { container, rerender } = render(<CartOfflineModal />);
    expect(screen.getByText('카트와 연결이 끊겼어요')).toBeInTheDocument();

    useCartConnectionStore.getState().applyConnection(true);
    rerender(<CartOfflineModal />);

    expect(container).toBeEmptyDOMElement();
  });
});
