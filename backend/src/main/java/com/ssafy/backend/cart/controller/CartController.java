package com.ssafy.backend.cart.controller;

import com.ssafy.backend.cart.service.CartService;
import com.ssafy.backend.cart.service.CartService.Response;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/carts")
public class CartController {

	private final CartService service;

	public CartController(CartService service) {
		this.service = service;
	}

	@GetMapping("/{cartId}")
	@Operation(operationId = "getCart", tags = "carts")
	public Response findById(@PathVariable Long cartId) {
		return service.findById(cartId);
	}
}
