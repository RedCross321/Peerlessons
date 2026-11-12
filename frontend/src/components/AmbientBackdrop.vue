<template>
  <div class="ambient-backdrop" aria-hidden="true"></div>
</template>

<style scoped>
.ambient-backdrop {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-color: var(--backdrop-line);
  -webkit-mask: url('/backdrop-topo.svg') center / cover no-repeat;
  mask: url('/backdrop-topo.svg') center / cover no-repeat;
}
</style>
