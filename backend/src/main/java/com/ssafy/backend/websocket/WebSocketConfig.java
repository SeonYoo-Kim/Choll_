package com.ssafy.backend.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

	private final CartWebSocketHandler cartWebSocketHandler;
	private final VideoRelayHandler videoRelayHandler;

	public WebSocketConfig(
		CartWebSocketHandler cartWebSocketHandler,
		VideoRelayHandler videoRelayHandler
	) {
		this.cartWebSocketHandler = cartWebSocketHandler;
		this.videoRelayHandler = videoRelayHandler;
	}

	@Override
	public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
		registry.addHandler(cartWebSocketHandler, "/ws/carts/*")
			.setAllowedOriginPatterns("http://localhost:*", "http://127.0.0.1:*");
		// 영상 릴레이: Jetson 발행(/video/publish), FE 시청(/video)
		// JPEG 프레임 크기 한도는 VideoRelayHandler가 세션별로 설정한다
		registry.addHandler(
				videoRelayHandler,
				"/ws/carts/*/video",
				"/ws/carts/*/video/publish"
			)
			.setAllowedOriginPatterns("*"); // Jetson(비브라우저)·FE 모두 허용
	}
}
