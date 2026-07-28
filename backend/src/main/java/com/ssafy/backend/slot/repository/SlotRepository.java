package com.ssafy.backend.slot.repository;

import com.ssafy.backend.slot.domain.Slot;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SlotRepository extends JpaRepository<Slot, Long> {

	@Query("""
		select slot
		from Slot slot
		left join fetch slot.bookCopy copy
		left join fetch copy.book
		left join fetch copy.bookshelf bookshelf
		left join fetch bookshelf.zone
		where slot.cart.id = :cartId
		order by slot.slotNumber
		""")
	List<Slot> findAllByCartId(@Param("cartId") Long cartId);

	@Query("""
		select slot
		from Slot slot
		left join fetch slot.bookCopy copy
		left join fetch copy.book
		left join fetch copy.bookshelf bookshelf
		left join fetch bookshelf.zone
		where slot.cart.id = :cartId
		  and slot.slotNumber = :slotNumber
		""")
	Optional<Slot> findByCartIdAndSlotNumber(
		@Param("cartId") Long cartId,
		@Param("slotNumber") int slotNumber
	);
}
