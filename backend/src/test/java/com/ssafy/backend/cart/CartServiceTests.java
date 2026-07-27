package com.ssafy.backend.cart;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.when;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.domain.CartOperationStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.cart.service.CartService;
import com.ssafy.backend.cart.service.CartService.Response;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CartServiceTests {

	@Mock
	private CartRepository repository;

	@Mock
	private Cart cart;

	private CartService service;

	@BeforeEach
	void setUp() {
		service = new CartService(repository);
	}

	@Test
	void findsOfflineIdleCart() {
		when(repository.findById(1L)).thenReturn(Optional.of(cart));
		when(cart.getId()).thenReturn(1L);
		when(cart.getName()).thenReturn("쫄래쫄래 카트");
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.OFFLINE);
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.IDLE);

		Response response = service.findById(1L);

		assertEquals(1L, response.id());
		assertEquals(CartConnectionStatus.OFFLINE, response.connectionStatus());
		assertEquals(CartOperationStatus.IDLE, response.operationStatus());
		assertNull(response.currentZoneId());
	}
}
