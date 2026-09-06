<script setup lang="ts">
const PATHS: Record<string, string> = {
  light: 'M9.5 18h5M10.5 21h3M12 3a6 6 0 0 0-3.7 10.7c.7.6 1.1 1.4 1.2 2.3h5c.1-.9.5-1.7 1.2-2.3A6 6 0 0 0 12 3z',
  media: 'M6.5 3.5h11a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1zM12 17a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM12 8h.01',
  tv: 'M3.5 6h17a1 1 0 0 1 1 1v9.5a1 1 0 0 1-1 1h-17a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zM8.5 21h7',
  camera: 'M3.5 8.5h17v10h-17zM12 16.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8.5 8.5l1.5-3h4l1.5 3',
  lock: 'M6 11h12v9.5H6zM9 11V8a3 3 0 0 1 6 0v3M12 15v2',
  cover: 'M4 4h16v3.5H4zM4 7.5h16M4 11.5h16M4 15.5h16M4 19.5h16M12 7.5v12',
  fan: 'M12 13.8a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6zM12 10.2c0-3.2 1.4-5.2 3.6-5.2 1.8 0 2.4 1.6 1 3.2-1.2 1.4-2.8 2-4.6 2zM12 13.8c0 3.2-1.4 5.2-3.6 5.2-1.8 0-2.4-1.6-1-3.2 1.2-1.4 2.8-2 4.6-2zM10.2 12c-3.2 0-5.2-1.4-5.2-3.6 0-1.8 1.6-2.4 3.2-1 1.4 1.2 2 2.8 2 4.6zM13.8 12c3.2 0 5.2 1.4 5.2 3.6 0 1.8-1.6 2.4-3.2 1-1.4-1.2-2-2.8-2-4.6z',
  sensor: 'M10 4.5a2 2 0 0 1 4 0v8.8a4 4 0 1 1-4 0zM12 9.5v8',
  motion: 'M12 13.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM7.5 7.5a6.5 6.5 0 0 0 0 9M16.5 7.5a6.5 6.5 0 0 1 0 9M4.5 4.5a10.5 10.5 0 0 0 0 15M19.5 4.5a10.5 10.5 0 0 1 0 15',
  contact: 'M5 3.5h10.5v17H5zM12.5 12h.01M15.5 3.5h3.5v17h-3.5',
  switch: 'M12 3.5v8.5M6.6 6.6a7.6 7.6 0 1 0 10.8 0',
  vacuum: 'M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM12 4v2',
  home: 'M3.5 11l8.5-7.5 8.5 7.5M5.5 9.5v10h13v-10',
  back: 'M14.5 5.5l-6.5 6.5 6.5 6.5',
  play: 'M8 5.5l10 6.5-10 6.5z',
  pause: 'M7.5 5h3.5v14H7.5zM13 5h3.5v14H13z',
  next: 'M6 5.5l9 6.5-9 6.5zM17 5v14',
  prev: 'M18 5.5l-9 6.5 9 6.5zM7 5v14',
  power: 'M12 3.5v8.5M6.6 6.6a7.6 7.6 0 1 0 10.8 0',
  volume: 'M4 9.5v5h3.5l5 4v-13l-5 4zM16 9a4.5 4.5 0 0 1 0 6',
}
const FILLED = new Set(['play', 'pause', 'next', 'prev'])
defineProps<{ name: string; size?: number }>()
</script>

<template>
  <svg :width="size ?? 22" :height="size ?? 22" viewBox="0 0 24 24" :fill="FILLED.has(name) ? 'currentColor' : 'none'"
       stroke="currentColor" :stroke-width="FILLED.has(name) ? 0.8 : 1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path :d="PATHS[name] ?? PATHS.switch" />
  </svg>
</template>
