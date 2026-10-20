/**
 * Title and description limits of the metadata helper (WP-56, UX audit C5). A title is shown with the site template
 * ("%s · DefenceGate", 14 characters) and search results show about 60 characters of it; a description about 160. A longer text is
 * cut at a word, never inside one, and ends in an ellipsis; one that fits is unchanged.
 */
export const TITLE_TEMPLATE_SUFFIX = ' · DefenceGate';
export const TITLE_MAX = 60 - TITLE_TEMPLATE_SUFFIX.length;
export const DESCRIPTION_MAX = 160;

export function trimAtWord(text: string, max: number): string {
  const t = text.trim();
  if (t.length <= max) return t;
  const room = t.slice(0, max - 1);
  // The cut falls on a space or a mark: the last word is whole. Otherwise it falls inside a word: that word goes.
  const at = /[\s,;:.)]/.test(t.charAt(max - 1)) ? room.length : room.search(/\s\S*$/);
  const head = (at > 0 ? room.slice(0, at) : room).replace(/[\s,;:.\-–(]+$/, '');
  return `${head}…`;
}

/**
 * A text cut where a phrase ends, so the tab and the search snippet do not stop mid-phrase (WP-59, re-audit NEW-5): the last whole
 * sentence that fits, else the part before the last colon, semicolon, dash or bracket that fits, followed by `end` ("." for a
 * description). A head shorter than `min` says too little: the text is then cut at a word with an ellipsis (trimAtWord).
 */
export function trimAtPhrase(text: string, max: number, min: number, end = ''): string {
  const t = text.trim();
  if (t.length <= max) return t;
  const room = t.slice(0, max + 1);
  const sentence = Math.max(...['. ', '? ', '! '].map((m) => room.lastIndexOf(m))) + 1;
  if (sentence >= min) return t.slice(0, sentence);
  // A colon, semicolon or dash ends a phrase before a bracket does ("... supply: each requirement, who issues it (in ..."). A quoted
  // search after the mark ("Tenders, page 2: “drone ...”") is what the view is: it is cut at a word, not dropped.
  for (const marks of [/(?:: |; | – | — )(?!“)/g, / \(/g]) {
    const clause = Math.max(-1, ...[...t.matchAll(marks)].map((m) => m.index ?? -1).filter((i) => i + end.length <= max));
    if (clause >= min) return `${t.slice(0, clause).replace(/[\s,]+$/, '')}${end}`;
  }
  return trimAtWord(t, max);
}
