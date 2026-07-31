const SLOTS_PER_ROW = 6;

/** 1~12번 슬롯을 카트 표기(A-01~B-06)로 변환한다. */
export function slotLabel(slotNumber: number): string {
  const rowIndex = Math.floor((slotNumber - 1) / SLOTS_PER_ROW);
  const position = ((slotNumber - 1) % SLOTS_PER_ROW) + 1;
  const row = String.fromCharCode('A'.charCodeAt(0) + rowIndex);

  return `${row}-${String(position).padStart(2, '0')}`;
}
