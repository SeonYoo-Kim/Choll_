package com.ssafy.backend.websocket;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PositionTestPublisherTest {

	@Mock
	private CartWebSocketHandler webSocketHandler;

	@Test
	void publishesImageCoordinatesForTheTestMap() {
		PositionTestPublisher publisher = new PositionTestPublisher(webSocketHandler, 1L, 2L);
		ArgumentCaptor<String> messageCaptor = ArgumentCaptor.forClass(String.class);

		publisher.publish();

		verify(webSocketHandler).send(eq(1L), messageCaptor.capture());
		assertThat(messageCaptor.getValue())
			.contains("\"type\":\"CART_POSITION_UPDATE\"")
			.contains("\"mapId\":2")
			.contains("\"x\":850.00")
			.contains("\"y\":300.00")
			.contains("\"yaw\":1.57")
			.contains("\"valid\":true");
	}
}
