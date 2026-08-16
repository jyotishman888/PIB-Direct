/** Today's date in Asia/Kolkata as YYYY-MM-DD, for filtering "today's releases".
 *
 * PIB publishes on IST. A visitor's local date can disagree with IST near
 * midnight in either direction, so "today" is computed against IST rather
 * than the browser's timezone — matching `scheduler_timezone` in the
 * backend's config.
 */
export function getTodayIST(): string {
  // en-CA formats as YYYY-MM-DD, which is exactly the date_from/date_to
  // shape the /articles endpoint already expects.
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date())
}
