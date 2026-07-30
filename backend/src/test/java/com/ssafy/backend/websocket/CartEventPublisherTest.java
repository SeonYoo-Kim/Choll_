package com.ssafy.backend.websocket;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.ObjectMapper;

@ExtendWith(MockitoExtension.class)
class CartEventPublisherTest {

	@Mock
	private CartWebSocketHandler webSocketHandler;

	@Test
	void wrapsPayloadInTypedEventJson() {
		CartEventPublisher publisher = new CartEventPublisher(
			webSocketHandler,
			new ObjectMapper()
		);

		publisher.publish(1L, "CART_POSITION_UPDATE", Map.of("x", 100.5));

		ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
		verify(webSocketHandler).send(eq(1L), captor.capture());
		assertThat(captor.getValue())
			.contains("\"type\":\"CART_POSITION_UPDATE\"")
			.contains("\"payload\"")
			.contains("\"x\":100.5");
	}
}
