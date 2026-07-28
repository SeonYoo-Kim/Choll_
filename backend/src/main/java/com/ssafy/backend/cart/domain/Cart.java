package com.ssafy.backend.cart.domain;

import com.ssafy.backend.zone.domain.Zone;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
	name = "carts",
	uniqueConstraints = @UniqueConstraint(name = "uk_cart_name", columnNames = "name")
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Cart {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@Column(nullable = false, length = 100)
	private String name;

	@Enumerated(EnumType.STRING)
	@Column(name = "connection_status", nullable = false, length = 20)
	private CartConnectionStatus connectionStatus;

	@Enumerated(EnumType.STRING)
	@Column(name = "operation_status", nullable = false, length = 20)
	private CartOperationStatus operationStatus;

	@Column(name = "position_x", precision = 12, scale = 6)
	private BigDecimal positionX;

	@Column(name = "position_y", precision = 12, scale = 6)
	private BigDecimal positionY;

	@ManyToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "current_zone_id")
	private Zone currentZone;

	@Column(name = "last_communication_at")
	private LocalDateTime lastCommunicationAt;

	public Cart(String name) {
		this.name = name;
		this.connectionStatus = CartConnectionStatus.OFFLINE;
		this.operationStatus = CartOperationStatus.IDLE;
	}

	public void updateStatus(
		CartConnectionStatus connectionStatus,
		CartOperationStatus operationStatus,
		LocalDateTime communicationAt
	) {
		this.connectionStatus = connectionStatus;
		this.operationStatus = operationStatus;
		this.lastCommunicationAt = communicationAt;
	}

	public void updatePosition(
		BigDecimal positionX,
		BigDecimal positionY,
		Zone currentZone,
		LocalDateTime communicationAt
	) {
		this.positionX = positionX;
		this.positionY = positionY;
		this.currentZone = currentZone;
		this.lastCommunicationAt = communicationAt;
	}
}
