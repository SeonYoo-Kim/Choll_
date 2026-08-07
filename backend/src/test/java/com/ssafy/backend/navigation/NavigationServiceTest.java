package com.ssafy.backend.navigation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.domain.CartOperationStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.map.domain.LibraryMap;
import com.ssafy.backend.map.repository.LibraryMapRepository;
import com.ssafy.backend.mqtt.command.MqttCommandPublisher;
import com.ssafy.backend.mqtt.position.PolygonZoneMatcher;
import com.ssafy.backend.mqtt.position.SlamCoordinateConverter;
import com.ssafy.backend.navigation.service.NavigationService;
import com.ssafy.backend.websocket.CartEventPublisher;
import com.ssafy.backend.zone.domain.Zone;
import com.ssafy.backend.zone.repository.ZoneRepository;
import java.math.BigDecimal;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import tools.jackson.databind.ObjectMapper;

@ExtendWith(MockitoExtension.class)
class NavigationServiceTest {

	@Mock
	private CartRepository cartRepository;

	@Mock
	private ZoneRepository zoneRepository;

	@Mock
	private LibraryMapRepository mapRepository;

	@Mock
	private CartEventPublisher eventPublisher;

	@Mock
	private ObjectProvider<MqttCommandPublisher> commandPublisherProvider;

	@Mock
	private MqttCommandPublisher commandPublisher;

	@Mock
	private Cart cart;

	@Mock
	private Zone zone;

	@Mock
	private LibraryMap map;

	private NavigationService service;

	@BeforeEach
	void setUp() {
		service = newService("pixels");
	}

	private NavigationService newService(String positionUnit) {
		return new NavigationService(
			cartRepository,
			zoneRepository,
			mapRepository,
			new SlamCoordinateConverter(),
			new PolygonZoneMatcher(new ObjectMapper()),
			eventPublisher,
			commandPublisherProvider,
			new ObjectMapper(),
			positionUnit,
			2L,
			0.5
		);
	}

	@Test
	void startsNavigationAndPublishesMoveCommandToZoneCenter() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(zone.getPolygonJson())
			.thenReturn("[[550,410],[1000,410],[1000,600],[550,600]]");
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);

		NavigationService.Response response = service.start(1L, 7L);

		assertThat(response.status()).isEqualTo("ACCEPTED");
		assertThat(response.destinationZoneId()).isEqualTo(7L);
		verify(cart).updateStatus(
			eq(CartConnectionStatus.ONLINE),
			eq(CartOperationStatus.NAVIGATING),
			any()
		);
		ArgumentCaptor<Object> command = ArgumentCaptor.forClass(Object.class);
		verify(commandPublisher).publish(command.capture());
		assertThat(command.getValue().toString())
			.contains("command=MOVE")
			.contains("zoneId=7")
			.contains("pixel=Pixel[x=775.0, y=505.0]")
			.contains("target=null");
		ArgumentCaptor<Object> event = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(
			eq(1L),
			eq("NAVIGATION_STATUS_UPDATED"),
			event.capture()
		);
		assertThat(event.getValue().toString()).contains("status=ACCEPTED");
	}

	@Test
	void metersModeIncludesSlamTargetConvertedFromPixels() {
		service = newService("meters");
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(zone.getPolygonJson())
			.thenReturn("[[550,410],[1000,410],[1000,600],[550,600]]");
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		// resolution 0.05 m/px, origin (-10, -10), 이미지 높이 600px
		when(map.getResolution()).thenReturn(new BigDecimal("0.05"));
		when(map.getOriginX()).thenReturn(new BigDecimal("-10"));
		when(map.getOriginY()).thenReturn(new BigDecimal("-10"));
		when(map.getHeight()).thenReturn(600);
		when(mapRepository.findById(2L)).thenReturn(Optional.of(map));

		service.start(1L, 7L);

		// 픽셀 (775, 505) → SLAM (-10+775*0.05, -10+(600-505)*0.05) = (28.75, -5.25)
		ArgumentCaptor<Object> command = ArgumentCaptor.forClass(Object.class);
		verify(commandPublisher).publish(command.capture());
		assertThat(command.getValue().toString())
			.contains("target=Target[x=28.75, y=-5.25]")
			.contains("pixel=Pixel[x=775.0, y=505.0]");
	}

	@Test
	void usesClickedPixelInsteadOfZoneCenterWhenProvided() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(zone.getPolygonJson())
			.thenReturn("[[550,410],[1000,410],[1000,600],[550,600]]");
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);

		// 구역 안을 누른 경우 — 좌표를 손대지 않는다
		service.start(1L, 7L, 612.0, 431.0);

		ArgumentCaptor<Object> command = ArgumentCaptor.forClass(Object.class);
		verify(commandPublisher).publish(command.capture());
		assertThat(command.getValue().toString())
			.contains("pixel=Pixel[x=612.0, y=431.0]");
	}

	@Test
	void snapsClickOutsideZoneToNearestPointInsideZone() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		// 0~100 정사각형 구역 (중심 50,50)
		when(zone.getPolygonJson()).thenReturn("[[0,0],[100,0],[100,100],[0,100]]");
		when(zone.getMap()).thenReturn(map);
		when(map.getResolution()).thenReturn(new BigDecimal("0.05"));
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);

		// 구역 왼쪽 밖(서가 위)을 누름 — 가장 가까운 경계는 (0,50)
		service.start(1L, 7L, -50.0, 50.0);

		// 경계에서 중심 쪽으로 여유 0.5m / 0.05m/px = 10px 안쪽
		ArgumentCaptor<Object> command = ArgumentCaptor.forClass(Object.class);
		verify(commandPublisher).publish(command.capture());
		assertThat(command.getValue().toString())
			.contains("zoneId=7")
			.contains("pixel=Pixel[x=10.0, y=50.0]");
	}

	@Test
	void keepsClickedPixelWhenZonePolygonIsUnreadable() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(zone.getPolygonJson()).thenReturn("not-json");
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);

		service.start(1L, 7L, 612.0, 431.0);

		ArgumentCaptor<Object> command = ArgumentCaptor.forClass(Object.class);
		verify(commandPublisher).publish(command.capture());
		assertThat(command.getValue().toString())
			.contains("pixel=Pixel[x=612.0, y=431.0]");
	}

	@Test
	void rejectsStartWhenCartIsOffline() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.OFFLINE);

		assertThatThrownBy(() -> service.start(1L, 7L))
			.isInstanceOf(InvalidDomainException.class)
			.hasMessageContaining("오프라인");
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void rejectsStartWhenNavigationIsAlreadyActive() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(zone.getPolygonJson())
			.thenReturn("[[550,410],[1000,410],[1000,600],[550,600]]");
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		service.start(1L, 7L);

		assertThatThrownBy(() -> service.start(1L, 7L))
			.isInstanceOf(InvalidDomainException.class)
			.hasMessageContaining("이미 진행 중");
	}

	@Test
	void cancelPublishesCancelCommandAndReturnsCartToIdle() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(zone.getPolygonJson())
			.thenReturn("[[550,410],[1000,410],[1000,600],[550,600]]");
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		long navigationId = service.start(1L, 7L).navigationId();

		service.cancel(1L);

		verify(cart).updateStatus(
			eq(CartConnectionStatus.ONLINE),
			eq(CartOperationStatus.IDLE),
			any()
		);
		ArgumentCaptor<Object> event = ArgumentCaptor.forClass(Object.class);
		// start(ACCEPTED)와 cancel(CANCELLED) 두 번 발행 — 마지막 캡처 검증
		verify(eventPublisher, org.mockito.Mockito.times(2)).publish(
			eq(1L),
			eq("NAVIGATION_STATUS_UPDATED"),
			event.capture()
		);
		assertThat(event.getAllValues().getLast().toString())
			.contains("status=CANCELLED")
			.contains("navigationId=" + navigationId);
	}

	@Test
	void cancelIsIdempotentWhenNothingIsActive() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));

		service.cancel(1L);

		verify(cart, never()).updateStatus(any(), any(), any());
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void cancelClearsStaleNavigatingStatusWithoutSession() {
		// 재시작으로 세션은 사라지고 DB 상태만 NAVIGATING으로 남은 경우
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.NAVIGATING);

		service.cancel(1L);

		verify(cart).updateStatus(any(), eq(CartOperationStatus.IDLE), any());
		// 취소할 실제 이동이 없으므로 MQTT·WS 발행은 없어야 한다
		verify(commandPublisher, never()).publish(any());
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void cartNavResultSucceededEndsSessionAndPublishesArrived() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(zone.getPolygonJson())
			.thenReturn("[[550,410],[1000,410],[1000,600],[550,600]]");
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		long navigationId = service.start(1L, 7L).navigationId();
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.NAVIGATING);

		service.applyCartNavResult(1L, "NAVIGATING");
		service.applyCartNavResult(1L, "SUCCEEDED");

		verify(cart).updateStatus(any(), eq(CartOperationStatus.IDLE), any());
		ArgumentCaptor<Object> event = ArgumentCaptor.forClass(Object.class);
		// ACCEPTED(start) → STARTED(NAVIGATING) → ARRIVED(SUCCEEDED)
		verify(eventPublisher, org.mockito.Mockito.times(3)).publish(
			eq(1L),
			eq("NAVIGATION_STATUS_UPDATED"),
			event.capture()
		);
		assertThat(event.getAllValues().get(1).toString()).contains("status=STARTED");
		assertThat(event.getAllValues().getLast().toString())
			.contains("status=ARRIVED")
			.contains("navigationId=" + navigationId);
		// 세션이 닫혔으므로 새 이동을 다시 받을 수 있다
		service.start(1L, 7L);
	}

	@Test
	void cartNavResultAbortedPublishesFailedWithReason() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(zone.getPolygonJson())
			.thenReturn("[[550,410],[1000,410],[1000,600],[550,600]]");
		when(commandPublisherProvider.getIfAvailable()).thenReturn(commandPublisher);
		service.start(1L, 7L);

		service.applyCartNavResult(1L, "ABORTED");

		ArgumentCaptor<Object> event = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher, org.mockito.Mockito.times(2)).publish(
			eq(1L),
			eq("NAVIGATION_STATUS_UPDATED"),
			event.capture()
		);
		assertThat(event.getAllValues().getLast().toString())
			.contains("status=FAILED")
			.contains("주행을 포기");
	}

	@Test
	void cartNavResultWithoutSessionOnlyReconcilesCartStatus() {
		// REST 취소가 먼저 세션을 정리한 뒤 카트의 CANCELED 확인 응답이 도착한 경우 —
		// 이벤트를 중복 발행하지 않고 DB 상태만 정리한다
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(cart.getOperationStatus()).thenReturn(CartOperationStatus.NAVIGATING);

		service.applyCartNavResult(1L, "CANCELED");

		verify(cart).updateStatus(any(), eq(CartOperationStatus.IDLE), any());
		verify(eventPublisher, never()).publish(any(), any(), any());
	}

	@Test
	void cartNavResultIdleAndUnknownAreIgnored() {
		service.applyCartNavResult(1L, "IDLE");
		service.applyCartNavResult(1L, "WARMING_UP");

		verify(eventPublisher, never()).publish(any(), any(), any());
		verify(cart, never()).updateStatus(any(), any(), any());
	}

	@Test
	void startsWithoutMqttWhenPublisherIsAbsent() {
		when(cartRepository.findById(1L)).thenReturn(Optional.of(cart));
		when(zoneRepository.findById(7L)).thenReturn(Optional.of(zone));
		when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.ONLINE);
		when(zone.getPolygonJson())
			.thenReturn("[[550,410],[1000,410],[1000,600],[550,600]]");
		when(commandPublisherProvider.getIfAvailable()).thenReturn(null);

		NavigationService.Response response = service.start(1L, 7L);

		assertThat(response.status()).isEqualTo("ACCEPTED");
		verify(eventPublisher).publish(eq(1L), eq("NAVIGATION_STATUS_UPDATED"), any());
	}
}
