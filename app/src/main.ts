import { createApp } from 'vue'
import { vHold } from './hold'
import '@fontsource-variable/instrument-sans'
/* Wall's own typeface, and the only layout that brings one. Loaded with the
   rest rather than when the layout is picked: it is one variable face, the same
   order of weight as the two already here, and a panel that swapped its type a
   second after waking would be worse than one that carries 30KB it might not
   use. See layout.ts for why a layout gets to decide this at all. */
import '@fontsource-variable/plus-jakarta-sans'
import '@fontsource/instrument-serif'
import '@fontsource/instrument-serif/400-italic.css'
import './panel.css'
import App from './App.vue'
createApp(App).directive('hold', vHold).mount('#app')
