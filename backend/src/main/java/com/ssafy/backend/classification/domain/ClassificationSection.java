package com.ssafy.backend.classification.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.math.BigDecimal;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
	name = "classification_sections",
	uniqueConstraints = @UniqueConstraint(
		name = "uk_classification_section_code",
		columnNames = "code"
	)
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ClassificationSection {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@Column(nullable = false, length = 20)
	private String code;

	@Column(nullable = false, length = 100)
	private String name;

	@ManyToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "parent_id")
	private ClassificationSection parent;

	@Column(nullable = false)
	private int depth;

	@Column(nullable = false, precision = 10, scale = 5)
	private BigDecimal startNumber;

	@Column(nullable = false, precision = 10, scale = 5)
	private BigDecimal endNumber;

	public ClassificationSection(
		String code,
		String name,
		ClassificationSection parent,
		BigDecimal startNumber,
		BigDecimal endNumber
	) {
		update(code, name, parent, startNumber, endNumber);
	}

	public void update(
		String code,
		String name,
		ClassificationSection parent,
		BigDecimal startNumber,
		BigDecimal endNumber
	) {
		this.code = code;
		this.name = name;
		this.parent = parent;
		this.depth = parent == null ? 0 : parent.getDepth() + 1;
		this.startNumber = startNumber;
		this.endNumber = endNumber;
	}
}
