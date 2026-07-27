package com.ssafy.backend.slot.domain;

import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.cart.domain.Cart;
import jakarta.persistence.CheckConstraint;
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
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
	name = "slots",
	uniqueConstraints = {
		@UniqueConstraint(
			name = "uk_slot_cart_number",
			columnNames = {"cart_id", "slot_number"}
		),
		@UniqueConstraint(name = "uk_slot_book_copy", columnNames = "book_copy_id")
	},
	check = @CheckConstraint(
		name = "ck_slot_number",
		constraint = "slot_number between 1 and 30"
	)
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Slot {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "cart_id", nullable = false)
	private Cart cart;

	@Column(name = "slot_number", nullable = false)
	private int slotNumber;

	@Enumerated(EnumType.STRING)
	@Column(nullable = false, length = 20)
	private SlotStatus status;

	@OneToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "book_copy_id")
	private BookCopy bookCopy;

	@Column(name = "last_scanned_at")
	private LocalDateTime lastScannedAt;

	public Slot(Cart cart, int slotNumber) {
		this.cart = cart;
		this.slotNumber = slotNumber;
		this.status = SlotStatus.EMPTY;
	}

	public void assignBook(BookCopy bookCopy, LocalDateTime scannedAt) {
		this.bookCopy = bookCopy;
		this.status = SlotStatus.OCCUPIED;
		this.lastScannedAt = scannedAt;
	}

	public void clear(LocalDateTime scannedAt) {
		this.bookCopy = null;
		this.status = SlotStatus.EMPTY;
		this.lastScannedAt = scannedAt;
	}

	public void updateStatus(SlotStatus status, LocalDateTime scannedAt) {
		this.status = status;
		this.lastScannedAt = scannedAt;
	}
}
