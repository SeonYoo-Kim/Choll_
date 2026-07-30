package com.ssafy.backend.task.domain;

import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.cart.domain.Cart;
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
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 도서 정리 작업 단위. 카트에 책이 실리면(RFID DETECTED) 생성되고,
 * 책이 제거되면(REMOVED = 서가에 꽂음) 완료 처리된다.
 */
@Getter
@Entity
@Table(name = "sorting_tasks")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class SortingTask {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "cart_id", nullable = false)
	private Cart cart;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "book_copy_id", nullable = false)
	private BookCopy bookCopy;

	@Enumerated(EnumType.STRING)
	@Column(nullable = false, length = 20)
	private SortingTaskStatus status;

	@Column(name = "created_at", nullable = false)
	private LocalDateTime createdAt;

	@Column(name = "completed_at")
	private LocalDateTime completedAt;

	public SortingTask(Cart cart, BookCopy bookCopy, LocalDateTime createdAt) {
		this.cart = cart;
		this.bookCopy = bookCopy;
		this.status = SortingTaskStatus.ACTIVE;
		this.createdAt = createdAt;
	}

	public void complete(LocalDateTime completedAt) {
		this.status = SortingTaskStatus.COMPLETED;
		this.completedAt = completedAt;
	}
}
