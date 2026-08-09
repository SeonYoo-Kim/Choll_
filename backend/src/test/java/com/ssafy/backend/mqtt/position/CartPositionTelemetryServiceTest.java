package com.ssafy.backend.mqtt.position;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.led.service.SlotLedService;
import com.ssafy.backend.map.domain.LibraryMap;
import com.ssafy.backend.map.repository.LibraryMapRepository;
import com.ssafy.backend.mqtt.heartbeat.CartConnectionService;
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
	private CartConnectionService connectionService;

	@Mock
	private LibraryMapRepository mapRepository;

	@Mock
	private SlotLedService slotLedService;

	@Mock
	private Cart cart;

	@Mock
	private Zone zone;

	@Mock
	private LibraryMap map;

	private CartPositionTelemetryService service;

	private CartPositionTelemetryService serviceWithUnit(String unit) {
		return new CartPositionTelemetryService(
			cartRepository,
			new RecentPositionBuffer(),
			zoneLocator,
			zoneTracker,
			eventPublisher,
			connectionService,
			mapRepository,
			new SlamCoordinateConverter(),
			slotLedService,
			unit,
			2L
		);
	}

	@BeforeEach
	void setUp() {
		service = serviceWithUnit("pixels");
	}

	@Test
	void publishesCartPositionUpdateEventWithZeroYawWhenNotSent() {
		PositionSample sample = new PositionSample(
			1L,
			new BigDecimal("100.5"),
			new BigDecimal("200.25"),
			null,
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

		verify(connectionService).markAlive(
			eq(cart),
			org.mockito.ArgumentMatchers.any(java.time.LocalDateTime.class)
		);
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
	void relaysYawAsIsInPixelsMode() {
		// pixels 모드는 좌표 무변환 — 방향도 그대로 중계한다 (수동 테스트 호환)
		PositionSample sample = new PositionSample(
			1L,
			new BigDecimal("100"),
			new BigDecimal("200"),
			new BigDecimal("0.0591"),
			Instant.parse("2026-08-08T18:14:39.719Z")
		);
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneLocator.locate(sample.x(), sample.y())).thenReturn(Optional.empty());
		when(zoneTracker.observe(1L, null))
			.thenReturn(new StableZoneTracker.Decision(false));
		when(cart.getCurrentZone()).thenReturn(null);

		service.accept(sample);

		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(eq(1L), eq("CART_POSITION_UPDATE"), captor.capture());
		assertThat(captor.getValue().toString()).contains("yaw=0.0591");
	}

	@Test
	void convertsYawThroughMapTransformInMetersMode() {
		service = serviceWithUnit("meters");
		// 기본식(세로반전) 지도 — 세계 CCW+ 0.5rad은 이미지(y 아래)에서 -0.5rad이 된다
		PositionSample sample = new PositionSample(
			1L,
			BigDecimal.ZERO,
			BigDecimal.ZERO,
			new BigDecimal("0.5"),
			Instant.parse("2026-08-08T18:14:39.719Z")
		);
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(mapRepository.findById(2L)).thenReturn(Optional.of(map));
		when(map.getResolution()).thenReturn(new BigDecimal("0.05"));
		when(map.getOriginX()).thenReturn(new BigDecimal("-10"));
		when(map.getOriginY()).thenReturn(new BigDecimal("-10"));
		when(map.getHeight()).thenReturn(600);
		when(map.getId()).thenReturn(2L);
		when(zoneLocator.locate(
			org.mockito.ArgumentMatchers.any(),
			org.mockito.ArgumentMatchers.any()
		)).thenReturn(Optional.empty());
		when(zoneTracker.observe(1L, null))
			.thenReturn(new StableZoneTracker.Decision(false));
		when(cart.getCurrentZone()).thenReturn(null);

		service.accept(sample);

		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(eq(1L), eq("CART_POSITION_UPDATE"), captor.capture());
		assertThat(captor.getValue().toString()).contains("yaw=-0.5000");
	}

	@Test
	void convertsSlamMetersToImagePixelsWhenUnitIsMeters() {
		service = serviceWithUnit("meters");
		PositionSample sample = new PositionSample(
			1L,
			BigDecimal.ZERO,
			BigDecimal.ZERO,
			null,
			Instant.parse("2026-07-31T08:00:00Z")
		);
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(mapRepository.findById(2L)).thenReturn(Optional.of(map));
		// resolution 0.05 m/px, origin (-10, -10), 높이 600 → SLAM (0,0)m = 픽셀 (200, 400)
		when(map.getResolution()).thenReturn(new BigDecimal("0.05"));
		when(map.getOriginX()).thenReturn(new BigDecimal("-10"));
		when(map.getOriginY()).thenReturn(new BigDecimal("-10"));
		when(map.getHeight()).thenReturn(600);
		when(map.getId()).thenReturn(2L);
		when(zoneLocator.locate(
			org.mockito.ArgumentMatchers.any(),
			org.mockito.ArgumentMatchers.any()
		)).thenReturn(Optional.empty());
		when(zoneTracker.observe(1L, null))
			.thenReturn(new StableZoneTracker.Decision(false));
		when(cart.getCurrentZone()).thenReturn(null);

		service.accept(sample);

		// 구역 판정도 변환된 픽셀 좌표로 수행돼야 한다
		verify(zoneLocator).locate(
			org.mockito.ArgumentMatchers.argThat(v -> v.compareTo(new BigDecimal("200")) == 0),
			org.mockito.ArgumentMatchers.argThat(v -> v.compareTo(new BigDecimal("400")) == 0)
		);
		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(
			eq(1L),
			eq("CART_POSITION_UPDATE"),
			captor.capture()
		);
		assertThat(captor.getValue().toString())
			.contains("mapId=2")
			.contains("x=200")
			.contains("y=400");
	}

	@Test
	void requestsSlotLightingWhenEnteringANewZone() {
		PositionSample sample = new PositionSample(
			1L,
			new BigDecimal("10"),
			new BigDecimal("20"),
			null,
			Instant.parse("2026-08-03T05:00:00Z")
		);
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneLocator.locate(sample.x(), sample.y())).thenReturn(Optional.of(zone));
		when(zone.getId()).thenReturn(5L);
		when(zoneTracker.observe(1L, 5L))
			.thenReturn(new StableZoneTracker.Decision(true));
		when(cart.getCurrentZone()).thenReturn(null);
		when(zone.getMap()).thenReturn(map);
		when(map.getId()).thenReturn(2L);

		service.accept(sample);

		verify(slotLedService).syncZoneLighting(1L, false);
	}

	@Test
	void doesNotRequestSlotLightingWhileStayingInTheSameZone() {
		PositionSample sample = new PositionSample(
			1L,
			new BigDecimal("11"),
			new BigDecimal("21"),
			null,
			Instant.parse("2026-08-03T05:00:01Z")
		);
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneLocator.locate(sample.x(), sample.y())).thenReturn(Optional.of(zone));
		when(zone.getId()).thenReturn(5L);
		when(zoneTracker.observe(1L, 5L))
			.thenReturn(new StableZoneTracker.Decision(true));
		when(cart.getCurrentZone()).thenReturn(zone);
		when(zone.getMap()).thenReturn(map);
		when(map.getId()).thenReturn(2L);

		service.accept(sample);

		verify(slotLedService, never()).syncZoneLighting(
			org.mockito.ArgumentMatchers.any(),
			org.mockito.ArgumentMatchers.anyBoolean()
		);
	}

	@Test
	void syncsLightingWithPreviousZoneFlagWhenLeavingAZone() {
		PositionSample sample = new PositionSample(
			1L,
			new BigDecimal("999"),
			new BigDecimal("999"),
			null,
			Instant.parse("2026-08-03T05:00:02Z")
		);
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneLocator.locate(sample.x(), sample.y())).thenReturn(Optional.empty());
		when(zoneTracker.observe(1L, null))
			.thenReturn(new StableZoneTracker.Decision(true));
		when(cart.getCurrentZone()).thenReturn(zone);

		service.accept(sample);

		// 직전에 구역 안이었으므로 leftLitZone=true — 서비스가 빈 목록으로 소등시킨다
		verify(slotLedService).syncZoneLighting(1L, true);
	}

	@Test
	void publishesEventWithNullMapIdWhenZoneIsUnknown() {
		PositionSample sample = new PositionSample(
			1L,
			new BigDecimal("999"),
			new BigDecimal("999"),
			null,
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
