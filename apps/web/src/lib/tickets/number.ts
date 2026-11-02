/** The short ticket number shown to people: the first 8 hex characters of the id, upper case (same rule as the API). */
export function ticketNumber(id: string): string {
  return id.replace(/-/g, "").slice(0, 8).toUpperCase();
}
