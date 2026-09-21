/* What the sheet is not allowed to forget.
 *
 * The panel's look is held together by the tokens at the top of panel.css, and the way it comes
 * apart is not dramatic: somebody writes the accent color out by hand instead of reaching for
 * --lamp, and a year later retuning the accent fixes nine screens out of eleven. There were 71
 * hand-written copies of it in here before this file existed. None of them were wrong; together
 * they meant the token had stopped being the source of the color.
 *
 * So these rules do not judge taste. They only insist that a value the house has already named is
 * spelled with its name -- which is the thing that keeps one screen looking like the next once the
 * styles live beside their components rather than in one sheet somebody reads end to end.
 */

/* The palette, exactly as :root declares it. A literal from this list is always a token that was
   spelled out the long way; anything NOT on it is a one-off shade the design actually wanted. */
const palette = [
  ['#e9b872', '--lamp'],
  ['233,\\s*184,\\s*114', '--lamp-rgb'],
  ['#b8863e', '--lamp-deep'],
  ['#2a1c07', '--lamp-ink'],
  ['42,\\s*28,\\s*7', '--lamp-ink-rgb'],
  ['#74c69d', '--live'],
  ['116,\\s*198,\\s*157', '--live-rgb'],
  ['#e08a8a', '--danger'],
  ['224,\\s*138,\\s*138', '--danger-rgb'],
  ['#f1eee8', '--ink'],
  ['#b9b5ad', '--ink-2'],
  ['#7f7d77', '--muted'],
  ['#0c0d10', '--bg'],
  ['#111318', '--bg-2'],
  ['26,\\s*28,\\s*34', '--surface-rgb'],
]

/* Properties that carry a color. box-shadow and background are in here because that is where the
   accent tends to get written out -- a glow under a lit card, a wash behind a chip. */
const colorProps = [
  'color',
  'background',
  'background-color',
  'background-image',
  'border-color',
  'border',
  'border-top',
  'border-bottom',
  'border-left',
  'border-right',
  'border-top-color',
  'border-bottom-color',
  'border-left-color',
  'border-right-color',
  'outline',
  'outline-color',
  'caret-color',
  'accent-color',
  'column-rule-color',
  'text-decoration-color',
  'stop-color',
  'box-shadow',
  'text-shadow',
  'fill',
  'stroke',
]

/* Only real color properties are checked, never custom properties, so the literals in :root --
   the one place they belong -- are not candidates for any of this. */
const colorRules = {}
for (const prop of colorProps) {
  colorRules[prop] = palette.map(([literal]) => new RegExp(literal, 'i'))
}

export default {
  /* Vue single-file components: the <style> blocks in them are held to the same rules as the sheet,
     which is the whole point -- a scoped block is where an untokenized value is least likely to be
     noticed by eye. */
  overrides: [{ files: ['**/*.vue'], customSyntax: 'postcss-html' }],

  rules: {
    /* A color the house has named, written out by hand. */
    'declaration-property-value-disallowed-list': {
      ...colorRules,
      /* The radius scale is three steps and they are declared. A literal that IS one of them is
         drift that happens to land on the right value; the next one lands on 14px and nobody
         notices. Off-scale radii are deliberately still allowed -- this panel is hand-tuned and
         snapping them is a design decision, not a lint fix. */
      'border-radius': [/^(22|16|12)px$/],
    },

    /* The §4 bug, and the reason AGENTS.md tells you to grep before adding a block: panel.css is one
       flat global sheet, so a class name that already exists does not conflict loudly -- the later
       block silently restyles the OTHER component. Nothing else catches it: not tsc, not eslint, not
       e2e, because both screens still render. This does.
       
       A warning rather than an error, and `lint:css` caps the count in package.json at what is
       already here. The sheet came to this rule with 22, and they have been read through once: the
       test that matters is whether the two blocks set the SAME property, because only then does one
       silently win. Nineteen of them set different properties and simply compose -- untidy, spread
       across the sheet, harmless. Two more are the card-tone layer deliberately restating a value
       with a var() whose fallback is the original (`.room-card`, and the dimmer's track), which is
       the pattern that section is built on. The twenty-second was genuinely dead and is gone.

       So what is left is debt of the harmless kind, and the cap is here to stop it growing rather
       than to demand a sweep: fix one and it still passes, add one and it does not. If you add a
       block for a selector that already exists, you are almost certainly looking for the block that
       is already there. */
    'no-duplicate-selectors': [true, { severity: 'warning' }],
  },
}
