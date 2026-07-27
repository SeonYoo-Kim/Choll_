package com.ssafy.backend.cart.service;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.domain.CartOperationStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.zone.domain.Zone;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CartService {

	private final CartRepository repository;

	public CartService(CartRepository repository) {
		this.repository = repository;
	}

	public Response findById(Long id) {
		return Response.from(getCart(id));
	}

	public Cart getCart(Long id) {
		return repository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("카트", id));
	}

	public record Response(
		Long id,
		String name,
		CartConnectionStatus connectionStatus,
		CartOperationStatus operationStatus,
		BigDecimal positionX,
		BigDecimal positionY,
		Long currentZoneId,
		String currentZoneCode,
		String currentZoneName,
		LocalDateTime lastCommunicationAt
	) {
		public static Response from(Cart cart) {
			Zone currentZone = cart.getCurrentZone();
			return new Response(
				cart.getId(),
				cart.getName(),
				cart.getConnectionStatus(),
				cart.getOperationStatus(),
				cart.getPositionX(),
				cart.getPositionY(),
				currentZone == null ? null : currentZone.getId(),
				currentZone == null ? null : currentZone.getCode(),
				currentZone == null ? null : currentZone.getName(),
				cart.getLastCommunicationAt()
			);
		}
	}
}
