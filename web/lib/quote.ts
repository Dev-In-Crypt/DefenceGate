/**
 * A sentence copied from a document, as the page shows it. The documents are read from PDF text, which carries the
 * numbers of footnotes glued to the word before them ("Horizon Europe202", "investor201": UX walk-through U13). The stored quote
 * stays exact, because the quote check compares it with the document; only the display drops the digits.
 *
 * ponytail: only two or three digits that follow a lowercase letter and end a word are dropped. A one-digit footnote, a
 * footnote after a capital or a digit, and a number set apart by spaces ("mid-caps 196 established") stay, because they
 * cannot be told from a real number. Upgrade: keep the footnote positions at extraction time.
 */
export function cleanQuote(text: string): string {
  return text.replace(/(?<=[a-z])\d{2,3}(?=[\s.,;:)]|$)/g, '');
}
