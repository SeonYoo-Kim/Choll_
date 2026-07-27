package com.ssafy.backend.cart.service;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.zone.domain.Zone;
import io.swagger.v3.oas.annotations.media.Schema;
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

	@Schema(name = "CartDetail")
	public record Response(
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		Long id,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		String name,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		Status status,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		boolean online,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED, nullable = true)
		Long mapId,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED, nullable = true)
		Long currentZoneId,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED, nullable = true)
		String currentZoneName,
		@Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED)
		Position position,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED, nullable = true)
		LocalDateTime lastSeenAt
	) {
		public static Response from(Cart cart) {
			Zone currentZone = cart.getCurrentZone();
			return new Response(
				cart.getId(),
				cart.getName(),
				Status.from(cart),
				cart.getConnectionStatus() == CartConnectionStatus.ONLINE,
				currentZone == null ? null : currentZone.getMap().getId(),
				currentZone == null ? null : currentZone.getId(),
				currentZone == null ? null : currentZone.getName(),
				Position.from(cart.getPositionX(), cart.getPositionY()),
				cart.getLastCommunicationAt()
			);
		}
	}

	@Schema(name = "CartStatus")
	public enum Status {
		IDLE,
		MOVING,
		FOLLOWING,
		ERROR;

		private static Status from(Cart cart) {
			return switch (cart.getOperationStatus()) {
				case IDLE -> IDLE;
				case NAVIGATING -> MOVING;
				case FOLLOWING -> FOLLOWING;
				case ERROR -> ERROR;
			};
		}
	}

	@Schema(name = "CartPosition")
	public record Position(
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		BigDecimal x,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		BigDecimal y
	) {
		private static Position from(BigDecimal x, BigDecimal y) {
			return x == null || y == null ? null : new Position(x, y);
		}
	}
}
