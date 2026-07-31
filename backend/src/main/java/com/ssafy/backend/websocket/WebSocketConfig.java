package com.ssafy.backend.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

	private final CartWebSocketHandler cartWebSocketHandler;

	public WebSocketConfig(CartWebSocketHandler cartWebSocketHandler) {
		this.cartWebSocketHandler = cartWebSocketHandler;
	}

	@Override
	public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
		registry.addHandler(cartWebSocketHandler, "/ws/carts/*")
			.setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
	}
}
