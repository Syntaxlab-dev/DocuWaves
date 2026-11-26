// Drag and drop in the admin's content tree: sorting pages and categories,
// and dropping a page onto a category to move it there. Plain HTML5 drag
// events (no library); these are the parts worth testing on their own.

/** What a dragged page row carries: its id, for a drop on a category. */
export const PAGE_MIME = "application/x-docuwaves-page";
/** What a dragged category row carries. */
export const CATEGORY_MIME = "application/x-docuwaves-category";

/** `list` with `moving` taken out and put before (or after) `target`.
 *  Unchanged when either is missing or they are the same. */
export function reorder<T>(list: T[], moving: T, target: T, after: boolean): T[] {
  if (moving === target || !list.includes(moving) || !list.includes(target)) return list;
  const rest = list.filter((item) => item !== moving);
  const at = rest.indexOf(target) + (after ? 1 : 0);
  return [...rest.slice(0, at), moving, ...rest.slice(at)];
}

/** Whether the pointer is over the lower half of `element`: drop after it. */
export function lowerHalf(event: { clientY: number }, element: Element): boolean {
  const box = element.getBoundingClientRect();
  return event.clientY > box.top + box.height / 2;
}

/** Whether a drag carries this kind of thing (only the types can be read
 *  while dragging; the data itself is for the drop). */
export function carries(event: { dataTransfer: DataTransfer | null }, mime: string): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes(mime);
}
