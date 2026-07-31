package com.ssafy.backend.slot;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.service.CartService;
import com.ssafy.backend.slot.domain.Slot;
import com.ssafy.backend.slot.domain.SlotStatus;
import com.ssafy.backend.slot.repository.SlotRepository;
import com.ssafy.backend.slot.service.SlotService;
import com.ssafy.backend.slot.service.SlotService.Response;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class SlotServiceTests {

	@Mock
	private SlotRepository repository;

	@Mock
	private CartService cartService;

	@Mock
	private Cart cart;

	@Mock
	private Slot slot;

	private SlotService service;

	@BeforeEach
	void setUp() {
		service = new SlotService(repository, cartService);
	}

	@Test
	void findsAllEmptySlotsInNumberOrder() {
		when(cartService.getCart(1L)).thenReturn(cart);
		when(repository.findAllByCartId(1L)).thenReturn(List.of(slot));
		when(slot.getId()).thenReturn(10L);
		when(slot.getSlotNumber()).thenReturn(1);
		when(slot.getStatus()).thenReturn(SlotStatus.EMPTY);

		List<Response> responses = service.findAll(1L);

		assertEquals(1, responses.size());
		assertEquals(SlotService.Status.EMPTY, responses.getFirst().status());
		assertNull(responses.getFirst().book());
		verify(repository).findAllByCartId(1L);
	}

	@Test
	void findsSlotByNumber() {
		when(cartService.getCart(1L)).thenReturn(cart);
		when(repository.findByCartIdAndSlotNumber(1L, 12))
			.thenReturn(Optional.of(slot));
		when(slot.getId()).thenReturn(12L);
		when(slot.getSlotNumber()).thenReturn(12);
		when(slot.getStatus()).thenReturn(SlotStatus.EMPTY);

		Response response = service.findByNumber(1L, 12);

		assertEquals(12, response.slotNumber());
		assertNull(response.book());
	}
}
