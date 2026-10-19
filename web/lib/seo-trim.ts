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
