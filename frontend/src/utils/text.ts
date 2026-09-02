// Recipe names arrive lowercased with punctuation stripped by the source
// corpus, so "Ree Ree's Chicken" is stored as "ree ree s chicken".
//
// Reattaching the apostrophe is a guess. It is right often enough in this
// corpus to be worth making, but it will mangle any recipe legitimately
// containing a standalone "s" — that is the trade, made knowingly.
export function titleCase(name: string): string {
  return name
    .replace(/\bs\b/g, "'s")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    // The pass above capitalises the S it just inserted.
    .replace(/'S\b/g, "'s")
    .replace(/\s+/g, ' ')
    .trim()
}