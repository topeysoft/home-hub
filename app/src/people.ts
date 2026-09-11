/*
 * A person's face on the panel: their initials on a colour of their own. The
 * colour goes by their place in the household, so the same person reads the
 * same on the bar along the bottom and on the People page, and a house of two
 * never has two of the same. Warm first, as drawn.
 */
const TONES = [
  'linear-gradient(140deg, #8a7f6a, #4a4238)',
  'linear-gradient(140deg, #b98a5e, #6a4a2e)',
  'linear-gradient(140deg, #6f8f86, #35544c)',
  'linear-gradient(140deg, #7e7fa6, #3f405e)',
  'linear-gradient(140deg, #a87474, #5e3c3c)',
  'linear-gradient(140deg, #6f86a3, #354a5e)',
]
export const personTone = (i: number) => TONES[i % TONES.length]
export const initials = (n: string) => n.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]!.toUpperCase()).join('')
