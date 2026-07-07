<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { Network } from 'vis-network/standalone'

const props = defineProps({
  chart: {
    type: Object,
    default: () => ({ nodes: [], edges: [] }),
  },
})

const container = ref(null)
let network = null

const options = {
  nodes: {
    shape: 'dot',
    size: 14,
    font: { size: 13, color: '#374151' },
    borderWidth: 2,
  },
  groups: {
    paper: { color: { background: '#93c5fd', border: '#3b82f6' }, shape: 'dot' },
    topic: {
      color: { background: '#c4b5fd', border: '#7c3aed' },
      shape: 'box',
      font: { color: '#4c1d95', bold: true },
    },
  },
  edges: {
    color: { color: '#d1d5db', highlight: '#7c3aed' },
    smooth: { type: 'continuous' },
    width: 1,
  },
  physics: {
    enabled: true,
    barnesHut: { gravitationalConstant: -3000, springLength: 120 },
    stabilization: { iterations: 120 },
  },
  interaction: { hover: true, tooltipDelay: 120 },
}

function render() {
  if (!container.value) return
  const data = {
    nodes: props.chart?.nodes || [],
    edges: props.chart?.edges || [],
  }
  if (network) {
    network.setData(data)
  } else {
    network = new Network(container.value, data, options)
  }
}

onMounted(render)

watch(
  () => props.chart,
  () => render(),
  { deep: true },
)

onBeforeUnmount(() => {
  if (network) {
    network.destroy()
    network = null
  }
})

const hasData = () => (props.chart?.nodes || []).length > 0
</script>

<template>
  <div class="review-chart">
    <div class="chart-title">文献主题聚类</div>
    <div v-show="hasData()" ref="container" class="chart-canvas"></div>
    <div v-if="!hasData()" class="chart-empty">检索后展示这批论文的研究主题分布</div>
    <div v-if="hasData()" class="chart-legend">
      <span class="legend-item"><i class="dot paper"></i>论文</span>
      <span class="legend-item"><i class="dot topic"></i>研究主题</span>
    </div>
  </div>
</template>

<style scoped>
.review-chart {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px;
}

.chart-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
}

.chart-canvas {
  flex: 1;
  min-height: 320px;
  border-radius: 8px;
  background: #fafafa;
}

.chart-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  font-size: 0.9rem;
  text-align: center;
  padding: 24px;
}

.chart-legend {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 0.8rem;
  color: #6b7280;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}

.dot.paper {
  background: #93c5fd;
  border: 2px solid #3b82f6;
}

.dot.topic {
  background: #c4b5fd;
  border: 2px solid #7c3aed;
  border-radius: 3px;
}
</style>
