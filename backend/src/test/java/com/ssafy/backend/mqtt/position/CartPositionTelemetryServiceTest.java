package com.ssafy.backend.mqtt.position;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.map.domain.LibraryMap;
import com.ssafy.backend.websocket.CartEventPublisher;
import com.ssafy.backend.zone.domain.Zone;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CartPositionTelemetryServiceTest {

	@Mock
	private CartRepository cartRepository;

	@Mock
	private ZoneLocator zoneLocator;

	@Mock
	private StableZoneTracker zoneTracker;

	@Mock
	private CartEventPublisher eventPublisher;

	@Mock
	private Cart cart;

	@Mock
	private Zone zone;

	@Mock
	private LibraryMap map;

	private CartPositionTelemetryService service;

	@BeforeEach
	void setUp() {
		service = new CartPositionTelemetryService(
			cartRepository,
			new RecentPositionBuffer(),
			zoneLocator,
			zoneTracker,
			eventPublisher
		);
	}

	@Test
	void publishesCartPositionUpdateEventWithTemporaryYaw() {
		PositionSample sample = new PositionSample(
			1L,
			new BigDecimal("100.5"),
			new BigDecimal("200.25"),
			Instant.parse("2026-07-29T04:32:27.680Z")
		);
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneLocator.locate(sample.x(), sample.y())).thenReturn(Optional.of(zone));
		when(zone.getId()).thenReturn(5L);
		when(zoneTracker.observe(1L, 5L))
			.thenReturn(new StableZoneTracker.Decision(true));
		when(zone.getMap()).thenReturn(map);
		when(map.getId()).thenReturn(2L);

		service.accept(sample);

		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(
			eq(1L),
			eq("CART_POSITION_UPDATE"),
			captor.capture()
		);
		assertThat(captor.getValue().toString())
			.contains("mapId=2")
			.contains("x=100.5")
			.contains("y=200.25")
			.contains("yaw=0")
			.contains("valid=true");
	}

	@Test
	void publishesEventWithNullMapIdWhenZoneIsUnknown() {
		PositionSample sample = new PositionSample(
			1L,
			new BigDecimal("999"),
			new BigDecimal("999"),
			Instant.parse("2026-07-29T04:32:27.680Z")
		);
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneLocator.locate(sample.x(), sample.y())).thenReturn(Optional.empty());
		when(zoneTracker.observe(1L, null))
			.thenReturn(new StableZoneTracker.Decision(false));
		when(cart.getCurrentZone()).thenReturn(null);

		service.accept(sample);

		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(
			eq(1L),
			eq("CART_POSITION_UPDATE"),
			captor.capture()
		);
		assertThat(captor.getValue().toString()).contains("mapId=null");
	}
}
