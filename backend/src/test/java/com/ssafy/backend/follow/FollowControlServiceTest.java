package com.ssafy.backend.follow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.domain.CartOperationStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.follow.service.FollowControlService;
import com.ssafy.backend.mqtt.command.MqttCommandPublisher;
import com.ssafy.backend.websocket.CartEventPublisher;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;

@ExtendWith(MockitoExtension.class)
class FollowControlServiceTest {

	@Mock
	private CartRepository cartRepository;

	@Mock
	private CartEventPublisher eventPublisher;

	@Mock
	private ObjectProvider<MqttCommandPublisher> commandPublisherProvider;

	@Mock
	private MqttCommandPublisher commandPublisher;

	@Mock
	private Cart cart;

	private FollowControlService service;

	@BeforeEach
	void setUp() {
		service = new FollowControlService(
			cartRepository,
			eventPublisher,
			commandPublisherProvider
		);
	}

	private void givenOnlineIdleCart() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.IDLE);
	}

	@Test
	void startsFollowingAndPublishesFollowStartCommand() {
		givenOnlineIdleCart();
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);

		FollowControlService.Response response = service.start(1L);

		assertThat(response.status()).isEqualTo("FOLLOWING");
		verify(cart).updateStatus(
			eq(CartConnectionStatus.ONLINE),
			eq(CartOperationStatus.FOLLOWING),
			any()
		);
		ArgumentCaptor<Object> command = ArgumentCaptor.forClass(Object.class);
		verify(commandPublisher).publish(command.capture());
		assertThat(command.getValue().toString())
			.contains("command=FOLLOW_START")
			.contains("requestId=" + response.followId());
		ArgumentCaptor<Object> event = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(
			eq(1L),
			eq("FOLLOW_STATUS_UPDATED"),
			event.capture()
		);
		assertThat(event.getValue().toString()).contains("status=FOLLOWING");
	}

	@Test
	void rejectsStartWhenCartIsOffline() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.OFFLINE);

		assertThatThrownBy(() -> service.start(1L))
			.isInstanceOf(InvalidDomainException.class)
			.hasMessageContaining("오프라인");
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void rejectsStartWhileNavigating() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.NAVIGATING);

		assertThatThrownBy(() -> service.start(1L))
			.isInstanceOf(InvalidDomainException.class)
			.hasMessageContaining("이동 중");
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void rejectsStartWhenAlreadyFollowing() {
		givenOnlineIdleCart();
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		service.start(1L);

		assertThatThrownBy(() -> service.start(1L))
			.isInstanceOf(InvalidDomainException.class)
			.hasMessageContaining("이미 추종 중");
	}

	@Test
	void resumesWithSameFollowIdAfterPause() {
		givenOnlineIdleCart();
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		long followId = service.start(1L).followId();
		service.pause(1L);

		FollowControlService.Response resumed = service.start(1L);

		assertThat(resumed.followId()).isEqualTo(followId);
		assertThat(resumed.status()).isEqualTo("FOLLOWING");
	}

	@Test
	void pausePublishesFollowPauseCommandAndKeepsSessionAlive() {
		givenOnlineIdleCart();
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		long followId = service.start(1L).followId();

		FollowControlService.Response response = service.pause(1L);

		assertThat(response.followId()).isEqualTo(followId);
		assertThat(response.status()).isEqualTo("PAUSED");
		ArgumentCaptor<Object> command = ArgumentCaptor.forClass(Object.class);
		verify(commandPublisher, times(2)).publish(command.capture());
		assertThat(command.getAllValues().getLast().toString())
			.contains("command=FOLLOW_PAUSE");
		ArgumentCaptor<Object> event = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher, times(2)).publish(
			eq(1L),
			eq("FOLLOW_STATUS_UPDATED"),
			event.capture()
		);
		assertThat(event.getAllValues().getLast().toString()).contains("status=PAUSED");
		// 일시정지는 추종 세션 유지 — 카트 상태는 FOLLOWING에서 바뀌지 않는다 (start의 1회만)
		verify(cart, times(1)).updateStatus(any(), any(), any());
	}

	@Test
	void pauseIsIdempotentWhenAlreadyPaused() {
		givenOnlineIdleCart();
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		service.start(1L);
		service.pause(1L);

		FollowControlService.Response response = service.pause(1L);

		assertThat(response.status()).isEqualTo("PAUSED");
		// FOLLOW_PAUSE 재발행 없음 (START 1회 + PAUSE 1회)
		verify(commandPublisher, times(2)).publish(any());
	}

	@Test
	void rejectsPauseWhenNothingIsActive() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));

		assertThatThrownBy(() -> service.pause(1L))
			.isInstanceOf(InvalidDomainException.class)
			.hasMessageContaining("진행 중인 추종이 없어");
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void stopPublishesFollowStopCommandAndReturnsCartToIdle() {
		givenOnlineIdleCart();
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		long followId = service.start(1L).followId();

		service.stop(1L);

		verify(cart).updateStatus(
			eq(CartConnectionStatus.ONLINE),
			eq(CartOperationStatus.IDLE),
			any()
		);
		ArgumentCaptor<Object> command = ArgumentCaptor.forClass(Object.class);
		verify(commandPublisher, times(2)).publish(command.capture());
		assertThat(command.getAllValues().getLast().toString())
			.contains("command=FOLLOW_STOP")
			.contains("requestId=" + followId);
		ArgumentCaptor<Object> event = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher, times(2)).publish(
			eq(1L),
			eq("FOLLOW_STATUS_UPDATED"),
			event.capture()
		);
		assertThat(event.getAllValues().getLast().toString()).contains("status=STOPPED");
	}

	@Test
	void stopIsIdempotentWhenNothingIsActive() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));

		service.stop(1L);

		verify(cart, never()).updateStatus(any(), any(), any());
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void startsWithoutMqttWhenPublisherIsAbsent() {
		givenOnlineIdleCart();
		when(commandPublisherProvider.getIfAvailable()).thenReturn(null);

		FollowControlService.Response response = service.start(1L);

		assertThat(response.status()).isEqualTo("FOLLOWING");
		verify(eventPublisher).publish(eq(1L), eq("FOLLOW_STATUS_UPDATED"), any());
	}
}
