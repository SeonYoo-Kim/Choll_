package com.ssafy.backend.cart;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartOperationStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.cart.service.CartOperationStatusReconciler;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CartOperationStatusReconcilerTest {

	@Mock
	private CartRepository cartRepository;

	@Mock
	private Cart idleCart;

	@Mock
	private Cart navigatingCart;

	@Mock
	private Cart followingCart;

	@Test
	void resetsOrphanedNavigatingAndFollowingCartsToIdleOnStartup() {
		when(idleCart.getOperationStatus()).thenReturn(CartOperationStatus.IDLE);
		when(navigatingCart.getOperationStatus())
			.thenReturn(CartOperationStatus.NAVIGATING);
		when(followingCart.getOperationStatus())
			.thenReturn(CartOperationStatus.FOLLOWING);
		when(cartRepository.findAll())
			.thenReturn(List.of(idleCart, navigatingCart, followingCart));

		new CartOperationStatusReconciler(cartRepository).run(null);

		verify(navigatingCart).updateStatus(any(), eq(CartOperationStatus.IDLE), any());
		verify(followingCart).updateStatus(any(), eq(CartOperationStatus.IDLE), any());
		verify(idleCart, never()).updateStatus(any(), any(), any());
	}
}
