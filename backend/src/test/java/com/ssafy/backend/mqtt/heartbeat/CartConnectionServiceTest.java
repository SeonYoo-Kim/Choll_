package com.ssafy.backend.mqtt.heartbeat;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.domain.CartOperationStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.websocket.CartEventPublisher;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CartConnectionServiceTest {

	private static final long OFFLINE_TIMEOUT_SECONDS = 15L;

	@Mock
	private CartRepository cartRepository;

	@Mock
	private CartEventPublisher eventPublisher;

	@Mock
	private Cart cart;

	private CartConnectionService service;

	@BeforeEach
	void setUp() {
		service = new CartConnectionService(
			cartRepository,
			eventPublisher,
			OFFLINE_TIMEOUT_SECONDS
		);
	}

	@Test
	void publishesConnectionEventWhenHeartbeatTurnsOfflineCartOnline() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.OFFLINE);
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.IDLE);
		when(cart.getId()).thenReturn(1L);

		service.heartbeat(1L, Instant.parse("2026-07-30T04:00:00Z"));

		verify(cart).updateStatus(
			eq(CartConnectionStatus.ONLINE),
			eq(CartOperationStatus.IDLE),
			any(LocalDateTime.class)
		);
		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(
			eq(1L),
			eq("CART_CONNECTION_UPDATED"),
			captor.capture()
		);
		assertThat(captor.getValue().toString()).contains("online=true");
	}

	@Test
	void doesNotPublishWhenCartIsAlreadyOnline() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.IDLE);

		service.heartbeat(1L, Instant.parse("2026-07-30T04:00:00Z"));

		verify(cart).updateStatus(
			eq(CartConnectionStatus.ONLINE),
			eq(CartOperationStatus.IDLE),
			any(LocalDateTime.class)
		);
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void watchdogTurnsStaleOnlineCartOfflineAndPublishes() {
		when(cartRepository.findAllByConnectionStatus(CartConnectionStatus.ONLINE))
			.thenReturn(List.of(cart));
		when(cart.getLastCommunicationAt())
			.thenReturn(LocalDateTime.of(2000, 1, 1, 0, 0));
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.IDLE);
		when(cart.getId()).thenReturn(1L);

		service.markStaleCartsOffline();

		verify(cart).updateStatus(
			eq(CartConnectionStatus.OFFLINE),
			eq(CartOperationStatus.IDLE),
			any()
		);
		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(
			eq(1L),
			eq("CART_CONNECTION_UPDATED"),
			captor.capture()
		);
		assertThat(captor.getValue().toString()).contains("online=false");
	}

	@Test
	void watchdogKeepsRecentlySeenCartsOnline() {
		when(cartRepository.findAllByConnectionStatus(CartConnectionStatus.ONLINE))
			.thenReturn(List.of(cart));
		when(cart.getLastCommunicationAt())
			.thenReturn(LocalDateTime.now(java.time.ZoneId.of("Asia/Seoul")));

		service.markStaleCartsOffline();

		verify(cart, never()).updateStatus(any(), any(), any());
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void watchdogTreatsCartsWithoutAnyCommunicationAsStale() {
		when(cartRepository.findAllByConnectionStatus(CartConnectionStatus.ONLINE))
			.thenReturn(List.of(cart));
		when(cart.getLastCommunicationAt()).thenReturn(null);
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.IDLE);
		when(cart.getId()).thenReturn(1L);

		service.markStaleCartsOffline();

		verify(cart).updateStatus(
			eq(CartConnectionStatus.OFFLINE),
			eq(CartOperationStatus.IDLE),
			any()
		);
	}
}
