package com.ssafy.backend.cart.repository;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CartRepository extends JpaRepository<Cart, Long> {

	List<Cart> findAllByConnectionStatus(CartConnectionStatus connectionStatus);
}
