<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AmbientBackdrop from '@/components/AmbientBackdrop.vue'
import { pageTransition } from '@/motion'

const route = useRoute()

const showBackdrop = computed(() => route.name && route.name !== 'room')
</script>

<template>
  <AmbientBackdrop v-if="showBackdrop" />

  <RouterView v-slot="{ Component, route: viewRoute }">
    <Transition
      mode="out-in"
      :css="false"
      @enter="pageTransition.onEnter"
      @leave="pageTransition.onLeave"
    >
      <component :is="Component" :key="viewRoute.path" />
    </Transition>
  </RouterView>
</template>
