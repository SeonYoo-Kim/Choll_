package com.ssafy.backend.cart.service;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartOperationStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * BE 기동 시 카트 동작 상태의 재시작 잔재를 청소한다.
 * 이동·추종 세션은 인메모리(NavigationService·FollowControlService)라 프로세스가
 * 재시작하면 반드시 사라진다 — 그런데 DB의 operationStatus가 NAVIGATING/FOLLOWING으로
 * 남아 있으면 세션 없는 고아 상태가 되어 추종 시작 등이 계속 거부된다(2026-08-04 배포에서 실제 발생).
 * 기동 직후에는 어떤 세션도 존재할 수 없으므로 그런 상태는 전부 IDLE로 되돌리는 게 안전하다.
 */
@Component
public class CartOperationStatusReconciler implements ApplicationRunner {

	private static final Logger log =
		LoggerFactory.getLogger(CartOperationStatusReconciler.class);

	private final CartRepository cartRepository;

	public CartOperationStatusReconciler(CartRepository cartRepository) {
		this.cartRepository = cartRepository;
	}

	@Override
	@Transactional
	public void run(ApplicationArguments args) {
		for (Cart cart : cartRepository.findAll()) {
			CartOperationStatus status = cart.getOperationStatus();
			if (status == CartOperationStatus.NAVIGATING
				|| status == CartOperationStatus.FOLLOWING) {
				cart.updateStatus(
					cart.getConnectionStatus(),
					CartOperationStatus.IDLE,
					cart.getLastCommunicationAt()
				);
				log.info(
					"재시작 잔재 동작 상태 정리: cartId={}, {} -> IDLE",
					cart.getId(),
					status
				);
			}
		}
	}
}
