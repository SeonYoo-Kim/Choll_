package com.ssafy.backend.task.repository;

import com.ssafy.backend.task.domain.SortingTask;
import com.ssafy.backend.task.domain.SortingTaskStatus;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SortingTaskRepository extends JpaRepository<SortingTask, Long> {

	Optional<SortingTask> findByCartIdAndBookCopyIdAndStatus(
		Long cartId,
		Long bookCopyId,
		SortingTaskStatus status
	);

	long countByCartIdAndStatus(Long cartId, SortingTaskStatus status);
}
