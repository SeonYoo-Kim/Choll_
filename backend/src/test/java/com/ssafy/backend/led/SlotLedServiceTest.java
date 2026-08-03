package com.ssafy.backend.led;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.ssafy.backend.led.service.SlotLedService;
import com.ssafy.backend.mqtt.command.MqttCommandPublisher;
import com.ssafy.backend.slot.service.SlotService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;

@ExtendWith(MockitoExtension.class)
class SlotLedServiceTest {

	@Mock
	private SlotService slotService;

	@Mock
	private ObjectProvider<MqttCommandPublisher> commandPublisher;

	@Mock
	private MqttCommandPublisher publisher;

	private SlotLedService service() {
		return new SlotLedService(slotService, commandPublisher);
	}

	@Test
	void publishesTargetSlotNumbersOfTheCurrentZone() {
		when(slotService.findTargetSlotNumbers(1L)).thenReturn(List.of(1, 3, 5));
		when(commandPublisher.getIfAvailable()).thenReturn(publisher);

		service().syncZoneLighting(1L, false);

		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(publisher).publishLed(captor.capture());
		assertThat(captor.getValue().toString()).contains("slot_id=[1, 3, 5]");
	}

	@Test
	void publishesEmptyListToTurnOffWhenLeavingAZone() {
		when(slotService.findTargetSlotNumbers(1L)).thenReturn(List.of());
		when(commandPublisher.getIfAvailable()).thenReturn(publisher);

		service().syncZoneLighting(1L, true);

		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(publisher).publishLed(captor.capture());
		assertThat(captor.getValue().toString()).contains("slot_id=[]");
	}

	@Test
	void doesNotPublishWhenEnteringAZoneWithNoTargetFromOutside() {
		when(slotService.findTargetSlotNumbers(1L)).thenReturn(List.of());

		service().syncZoneLighting(1L, false);

		verifyNoInteractions(commandPublisher);
		verifyNoInteractions(publisher);
	}

	@Test
	void skipsSilentlyWhenMqttIsDisabled() {
		when(slotService.findTargetSlotNumbers(1L)).thenReturn(List.of(2));
		when(commandPublisher.getIfAvailable()).thenReturn(null);

		service().syncZoneLighting(1L, false);

		verify(publisher, never()).publishLed(org.mockito.ArgumentMatchers.any());
	}
}
