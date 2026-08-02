package com.ssafy.backend.follow;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.follow.service.FollowTargetService;
import com.ssafy.backend.mqtt.command.MqttCommandPublisher;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;

@ExtendWith(MockitoExtension.class)
class FollowTargetServiceTest {

	@Mock
	private CartRepository cartRepository;

	@Mock
	private ObjectProvider<MqttCommandPublisher> commandPublisherProvider;

	@Mock
	private MqttCommandPublisher commandPublisher;

	@Mock
	private Cart cart;

	private FollowTargetService service() {
		return new FollowTargetService(cartRepository, commandPublisherProvider);
	}

	@Test
	@DisplayName("타겟 선택은 SELECT_TARGET 명령을 MQTT로 발행하고 SENT를 반환한다")
	void publishesSelectTargetCommand() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);

		FollowTargetService.Response response = service().selectTarget(1L, 16L);

		verify(commandPublisher).publish(any());
		assertThat(response.trackId()).isEqualTo(16L);
		assertThat(response.status()).isEqualTo("SENT");
	}

	@Test
	@DisplayName("없는 카트면 404 예외를 던진다")
	void rejectsUnknownCart() {
		when(cartRepository.findById(9L)).thenReturn(Optional.empty());

		assertThatThrownBy(() -> service().selectTarget(9L, 16L))
			.isInstanceOf(ResourceNotFoundException.class);
	}

	@Test
	@DisplayName("MQTT 비활성 상태면 InvalidDomainException을 던진다")
	void rejectsWhenMqttDisabled() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(commandPublisherProvider.getIfAvailable()).thenReturn(null);

		assertThatThrownBy(() -> service().selectTarget(1L, 16L))
			.isInstanceOf(InvalidDomainException.class);
	}
}
