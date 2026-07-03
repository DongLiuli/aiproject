<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Network, DataSet } from 'vis-network/standalone'
import { graphAPI, papersAPI } from '@/api'
import { ArrowLeft, Loader2, RefreshCw, Trash2, Maximize2, Info, ListChecks, Check } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()

const loading = ref(false)
const errorMsg = ref('')
const raw = ref({ nodes: [], edges: [] })
const stats = ref(null)
const llmUsed = ref(false)

// 论文范围选择：候选论文列表 + 已选 ID（默认全选）+ 选择面板显隐
const allPapers = ref([])
const selectedPaperIds = ref(new Set())
const showPicker = ref(false)
const selectedCount = computed(() => selectedPaperIds.value.size)

// 关系类型显隐开关（默认全开）
const filters = reactive({ cites: true, uses_dataset: true, uses_method: true })

// 会话内手动纠错：被删除的节点 / 边（刷新即恢复，不落库）
const hiddenNodes = ref(new Set())
const hiddenEdges = ref(new Set())

// 选中项详情（右侧面板）
const selected = ref(null) // { kind:'node'|'edge', ... }

// 视图模式：2d = vis-network 力导向 / 3d = 3d-force-graph（Three.js/WebGL，可拖拽旋转）
const viewMode = ref('3d')

const container = ref(null) // 2D 画布
const container3d = ref(null) // 3D 画布
let network = null
let nodesDS = null
let edgesDS = null
let renderedEl = null // vis 实例当前挂载的容器；状态切换后容器被 v-if/v-else 重建，需据此判断是否重建实例
let fg3d = null // 3d-force-graph 实例
let rendered3dEl = null
let ro3d = null // 监听 3D 容器尺寸变化的 ResizeObserver（3d-force-graph@1.80 自身无 resize 处理）
let glowTexture = null // 节点光晕贴图（径向渐变，缓存复用）

// ---- 视觉配置 ----
const TYPE_STYLE = {
  paper: { color: '#667eea', shape: 'dot', label: '论文' },
  dataset: { color: '#10b981', shape: 'diamond', label: '数据集' },
  method: { color: '#f59e0b', shape: 'triangle', label: '方法/模型' },
}
const RELATION_LABEL = {
  cites: '引用',
  uses_dataset: '使用数据集',
  uses_method: '使用方法',
}

// 论文结构化信息：点击论文节点按需拉取 + 缓存（避免重复请求）
const paperInfoCache = new Map()
const paperInfo = ref(null)
const paperInfoLoading = ref(false)

// 选中聚焦高亮：选中节点时其邻居/边高亮，其余整体变暗
let highlightNodes = new Set()
let highlightLinks = new Set()
let controls3d = null
let infoAnimRaf = null // 选中信息卡片展开动画的 RAF 句柄
let ambientBlobs = [] // 背景辉光团（呼吸/漂移动画对象）
let ambientRaf = null // 背景辉光呼吸动画的 RAF 句柄

const paperCount = computed(() => stats.value?.papers ?? 0)
const visibleNodeCount = computed(
  () => raw.value.nodes.filter((n) => !hiddenNodes.value.has(n.id)).length,
)

function edgeKey(e, i) {
  return e.id || `e${i}:${e.source}->${e.target}:${e.relation}`
}

// 结构化字段可能是数组或字符串，统一成非空数组，供列表渲染
function piList(v) {
  if (!v) return []
  if (Array.isArray(v)) return v.filter(Boolean)
  return [v]
}

// 根据过滤/删除状态，构建 vis 用的节点与边数组
function buildVisData() {
  const visNodes = []
  for (const n of raw.value.nodes) {
    if (hiddenNodes.value.has(n.id)) continue
    const style = TYPE_STYLE[n.type] || TYPE_STYLE.paper
    visNodes.push({
      id: n.id,
      label: n.label.length > 28 ? n.label.slice(0, 27) + '…' : n.label,
      title: n.label, // 原生 hover tooltip
      shape: style.shape,
      color: {
        background: style.color,
        border: style.color,
        highlight: { background: style.color, border: '#1f2937' },
      },
      font: { color: n.type === 'paper' ? '#1f2937' : '#374151', size: 14 },
      size: n.type === 'paper' ? 18 : 13,
    })
  }
  const visibleIds = new Set(visNodes.map((n) => n.id))

  const visEdges = []
  raw.value.edges.forEach((e, i) => {
    const key = edgeKey(e, i)
    if (hiddenEdges.value.has(key)) return
    if (!filters[e.relation]) return
    // 两端节点都在（删节点后其边自动隐藏）
    if (!visibleIds.has(e.source) || !visibleIds.has(e.target)) return
    const isCite = e.relation === 'cites'
    visEdges.push({
      id: key,
      from: e.source,
      to: e.target,
      arrows: 'to',
      dashes: !isCite,
      color: { color: isCite ? '#6366f1' : '#9ca3af', highlight: '#1f2937' },
      width: isCite ? 2 : 1,
      label: isCite ? String(e.confidence ?? '') : '',
      font: { size: 11, color: '#6b7280', strokeWidth: 3, strokeColor: '#ffffff' },
      smooth: { type: 'continuous' },
    })
  })
  return { visNodes, visEdges }
}

function renderNetwork() {
  if (!container.value) return // 容器尚未挂载（如 loading 态下 graph-body 未进 DOM）时不渲染
  const { visNodes, visEdges } = buildVisData()
  nodesDS = new DataSet(visNodes)
  edgesDS = new DataSet(visEdges)
  const data = { nodes: nodesDS, edges: edgesDS }
  const options = {
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: { gravitationalConstant: -50, springLength: 120, springConstant: 0.08 },
      stabilization: { iterations: 150 },
    },
    interaction: { hover: true, tooltipDelay: 200, navigationButtons: false },
    nodes: { borderWidth: 2 },
    edges: { selectionWidth: 2 },
  }
  // 状态切换会让 v-else 的 graph-body 被重建为新 DOM，旧实例指向已脱离的容器 → 销毁重建
  if (network && renderedEl !== container.value) {
    network.destroy()
    network = null
  }
  if (network) {
    network.setData(data)
  } else {
    network = new Network(container.value, data, options)
    renderedEl = container.value
    network.on('click', onClick)
  }
}

// ---- 3D 渲染（3d-force-graph） ----
// 复用 raw + 过滤/删除状态，产出 { nodes, links }（力导向会自动布局，节点可拖拽）
function build3dData() {
  const nodes = []
  for (const n of raw.value.nodes) {
    if (hiddenNodes.value.has(n.id)) continue
    const style = TYPE_STYLE[n.type] || TYPE_STYLE.paper
    nodes.push({
      id: n.id,
      type: n.type,
      color: style.color,
      val: n.type === 'paper' ? 7 : 3.5, // 论文（主胞体）明显更大，子节点（末端）更小
      label: n.label, // hover 悬浮全称
      short: n.label.length > 18 ? n.label.slice(0, 17) + '…' : n.label,
    })
  }
  const visibleIds = new Set(nodes.map((n) => n.id))
  const links = []
  raw.value.edges.forEach((e, i) => {
    const key = edgeKey(e, i)
    if (hiddenEdges.value.has(key)) return
    if (!filters[e.relation]) return
    if (!visibleIds.has(e.source) || !visibleIds.has(e.target)) return
    const isCite = e.relation === 'cites'
    links.push({
      _key: key,
      source: e.source,
      target: e.target,
      relation: e.relation,
      color: isCite ? '#818cf8' : '#94a3b8',
      width: isCite ? 1.6 : 0.7,
      particles: isCite ? 4 : 2, // 沿边流动的粒子，增强灵动感
    })
  })
  // 度数：子节点是否为「枢纽」（被多篇引用）的判据，供标签常显降噪（B1）
  const deg = new Map()
  links.forEach((l) => {
    deg.set(l.source, (deg.get(l.source) || 0) + 1)
    deg.set(l.target, (deg.get(l.target) || 0) + 1)
  })
  nodes.forEach((n) => {
    n.degree = deg.get(n.id) || 0
  })
  return { nodes, links }
}

// 生成一张径向渐变「光晕」贴图（planet 辉光用）
function makeGlowTexture(THREE) {
  if (glowTexture) return glowTexture
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0, 'rgba(255,255,255,0.95)')
  g.addColorStop(0.25, 'rgba(255,255,255,0.45)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  glowTexture = new THREE.CanvasTexture(canvas)
  return glowTexture
}

// 字符串哈希 + 确定性随机（mulberry32）：让树突方向按节点 id 固定，重建不抖动
function hashStr(s) {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}
function seededRand(seed) {
  return function () {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// 生成一簇细短「树突」线段（从胞体表面向外放射；确定性，避免每次重建抖动）
function makeDendrites(THREE, r, color, id) {
  const rand = seededRand(hashStr(id))
  const count = 6
  const pos = new Float32Array(count * 6)
  for (let i = 0; i < count; i++) {
    const theta = rand() * Math.PI * 2
    const phi = Math.acos(2 * rand() - 1)
    const len = r * (2.2 + rand() * 1.6)
    const dx = Math.sin(phi) * Math.cos(theta)
    const dy = Math.sin(phi) * Math.sin(theta)
    const dz = Math.cos(phi)
    pos[i * 6] = dx * r
    pos[i * 6 + 1] = dy * r
    pos[i * 6 + 2] = dz * r
    pos[i * 6 + 3] = dx * len
    pos[i * 6 + 4] = dy * len
    pos[i * 6 + 5] = dz * len
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  const mat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.22 })
  return new THREE.LineSegments(geo, mat)
}

// —— 选中节点周围的信息卡片（点击后「放电式」展开）——
// 单行裁剪：给小标题用
function clipText(s, n = 42) {
  s = String(s || '').replace(/\s+/g, ' ').trim()
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}
// 折行：3D sprite 不会自动换行，长文按宽度切成多行、超出行数省略，避免糊成超宽一行
function wrapText(s, width = 20, maxLines = 4) {
  s = String(s || '').replace(/\s+/g, ' ').trim()
  if (!s) return ''
  const lines = []
  for (let i = 0; i < s.length && lines.length < maxLines; i += width) {
    lines.push(s.slice(i, i + width))
  }
  if (s.length > width * maxLines) {
    lines[maxLines - 1] = lines[maxLines - 1].slice(0, width - 1) + '…'
  }
  return lines.join('\n')
}

// 依当前选中节点，产出要在其周围展示的信息条目 [{label, text}]
function infoChipEntries() {
  const sel = selected.value
  if (!sel || sel.kind !== 'node') return []
  const out = []
  if (sel.type === 'paper') {
    // 论文（主节点）：只放摘要，保持简洁（其余字段在右侧面板/论文详情里看）
    const info = paperInfo.value
    if (!info && paperInfoLoading.value) {
      out.push({ label: '', text: '加载论文信息…' })
    } else if (info) {
      const abs = info.abstract || info.research_background || ''
      out.push({ label: '摘要', text: abs || '（暂无摘要）', width: 22, maxLines: 7 })
    }
  } else {
    // 子节点（数据集/方法）：只给「被 N 篇论文使用」，论文明细收进面板/点击展开，不在节点旁堆砌
    out.push({ label: '', text: `被 ${usedByPapers.value.length} 篇论文使用` })
  }
  return out.slice(0, 7)
}

// 单张信息卡：深色圆角背景 + 类型色边框；label 作为彩色小标题浮在上方；正文自动折行
function makeChip(THREE, SpriteText, entry, color) {
  const chip = new THREE.Group()
  const wrapped = wrapText(entry.text, entry.width || 20, entry.maxLines || 4)
  const lines = wrapped ? wrapped.split('\n').length : 1
  const bodyH = 1.8
  const body = new SpriteText(wrapped)
  body.textHeight = bodyH
  body.color = '#e8eeff'
  body.backgroundColor = 'rgba(10,14,30,0.82)'
  body.padding = 1.6
  body.borderRadius = 2
  body.borderWidth = 0.4
  body.borderColor = color
  chip.add(body)
  if (entry.label) {
    const head = new SpriteText(clipText(entry.label, 22))
    head.textHeight = 1.7
    head.color = color
    head.fontWeight = 'bold'
    head.position.set(0, (lines * bodyH) / 2 + 2.2, 0)
    chip.add(head)
  }
  return chip
}

// 放电式展开动画：卡片从胞体中心向外滑出 + 放大 + 淡入（easeOutCubic）
function animateInfoIn(wrap, targets) {
  if (infoAnimRaf) cancelAnimationFrame(infoAnimRaf)
  const start = performance.now()
  const dur = 520
  const ease = (t) => 1 - Math.pow(1 - t, 3)
  const step = (now) => {
    const e = ease(Math.min(1, (now - start) / dur))
    wrap.children.forEach((chip, i) => {
      const tg = targets[i]
      if (tg) chip.position.set(tg.x * e, tg.y * e, tg.z * e)
      chip.scale.setScalar(0.0001 + e)
      chip.traverse((o) => {
        if (o.material) {
          o.material.transparent = true
          o.material.opacity = e
        }
      })
    })
    if (e < 1) infoAnimRaf = requestAnimationFrame(step)
    else infoAnimRaf = null
  }
  infoAnimRaf = requestAnimationFrame(step)
}

// 选中节点的 3D 对象需要重建时（如论文信息异步到达后）重新套用访问器
function refresh3dNodeObjects() {
  if (viewMode.value === '3d' && fg3d) fg3d.nodeThreeObject(fg3d.nodeThreeObject())
}

// 氛围场：节点后方几团超大彩色辉光（神经组织生物场感），带呼吸 + 极缓漂移，只加一次
function addAmbientField(THREE) {
  const scene = fg3d.scene()
  if (!scene || scene.userData.__ambient) return
  scene.userData.__ambient = true
  const tex = makeGlowTexture(THREE)
  const specs = [
    { color: '#3b4fd8', pos: [-220, 120, -520], scale: 900, opacity: 0.14 },
    { color: '#7c3aed', pos: [240, -170, -540], scale: 820, opacity: 0.11 },
    { color: '#0ea5a5', pos: [40, 260, -500], scale: 680, opacity: 0.085 },
  ]
  ambientBlobs = []
  specs.forEach((b, i) => {
    const sp = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: tex,
        color: b.color,
        transparent: true,
        opacity: b.opacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        depthTest: false,
      }),
    )
    sp.position.set(b.pos[0], b.pos[1], b.pos[2])
    sp.scale.set(b.scale, b.scale, 1)
    sp.renderOrder = -10 // 永远画在最底层
    scene.add(sp)
    ambientBlobs.push({
      sp,
      basePos: b.pos.slice(),
      baseScale: b.scale,
      baseOpacity: b.opacity,
      // 各团错开相位/速度，避免整齐划一 → 有机呼吸感
      phase: i * 2.1,
      speed: 0.32 + i * 0.11, // 呼吸速度（慢，周期约 12~20s）
      driftPhase: i * 1.7,
      driftSpeed: 0.11 + i * 0.05,
    })
  })
  startAmbientBreathing()
}

// 辉光呼吸 + 漂移动画（独立 RAF；fg3d 自身的渲染循环会把变化画出来）
function startAmbientBreathing() {
  if (ambientRaf) return
  const tick = (now) => {
    const t = now / 1000
    for (const b of ambientBlobs) {
      const s = Math.sin(t * b.speed + b.phase)
      // 呼吸：透明度大幅起伏、尺度轻微胀缩
      b.sp.material.opacity = b.baseOpacity * (0.55 + 0.55 * s)
      const sc = b.baseScale * (1 + 0.1 * s)
      b.sp.scale.set(sc, sc, 1)
      // 极缓李萨如漂移
      const d = t * b.driftSpeed + b.driftPhase
      b.sp.position.set(
        b.basePos[0] + Math.sin(d) * 55,
        b.basePos[1] + Math.cos(d * 0.8) * 40,
        b.basePos[2],
      )
    }
    ambientRaf = requestAnimationFrame(tick)
  }
  ambientRaf = requestAnimationFrame(tick)
}

// （神经元骨架期：暂不加星野 / 分层参考盘等背景装饰，保持克制）

async function render3d() {
  if (!container3d.value) return
  // 懒加载重依赖（Three.js / 后期特效），只在进入 3D 视图时拉取，不拖慢首页
  const [{ default: ForceGraph3D }, { default: SpriteText }, THREE, { UnrealBloomPass }] =
    await Promise.all([
      import('3d-force-graph'),
      import('three-spritetext'),
      import('three'),
      import('three/examples/jsm/postprocessing/UnrealBloomPass.js'),
    ])
  const data = build3dData()
  // 容器被 v-if/v-else 重建过 → 重建实例
  if (fg3d && rendered3dEl !== container3d.value) {
    fg3d._destructor?.()
    fg3d = null
    ro3d?.disconnect()
    ro3d = null
  }
  if (!fg3d) {
    fg3d = ForceGraph3D({ controlType: 'orbit' })(container3d.value)
      .backgroundColor('#06070f')
      .showNavInfo(false)
      // 关闭节点拖拽（治本）：three@0.185 下，拖拽结束时 3d-force-graph 会派发一个假 pointerup，
      // OrbitControls.onPointerUp 读不到指针坐标而抛 TypeError，打断点击 → onNodeClick 不触发 → 面板不出详情。
      // DragControls 仅在 enableNodeDrag 为真时创建，关掉即根除该崩溃；旋转/缩放/点击均不受影响。
      .enableNodeDrag(false)
      .nodeRelSize(4)
      .nodeVal((n) => n.val)
      // 选中时非高亮节点压暗（神经元「未激活」）
      .nodeColor((n) =>
        highlightNodes.size === 0 || highlightNodes.has(n.id) ? n.color : '#2a3350',
      )
      .nodeOpacity(0.95)
      .nodeResolution(16)
      .nodeLabel((n) => n.label) // hover 原生 tooltip
      .nodeThreeObjectExtend(true) // 保留默认球体作为「胞体」，叠加柔光 + 标签
      .nodeThreeObject((n) => {
        const group = new THREE.Group()
        const r = n.val
        const isPaper = n.type === 'paper'
        const dimmed = highlightNodes.size > 0 && !highlightNodes.has(n.id)
        const active = highlightNodes.has(n.id) // 当前被选中或其邻居
        // 柔和光晕：论文（主胞体）亮，子节点（末端）明显更暗更小
        const baseOpacity = isPaper ? 0.5 : 0.22
        const halo = new THREE.Sprite(
          new THREE.SpriteMaterial({
            map: makeGlowTexture(THREE),
            color: n.color,
            transparent: true,
            opacity: dimmed ? 0.08 : baseOpacity,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          }),
        )
        const hs = isPaper ? r * 3.6 : r * 2.4
        halo.scale.set(hs, hs, 1)
        group.add(halo)
        // 论文加克制的「树突」触须（低透明度，激活时略亮）
        if (isPaper && !dimmed) {
          const dend = makeDendrites(THREE, r, n.color, n.id)
          dend.material.opacity = active ? 0.4 : 0.2
          group.add(dend)
        }
        // 标签：论文（主题）常显、更大更亮；
        // 数据集/方法只有「枢纽」（被≥2篇引用）才常显名，长尾仅激活时显 —— 降低分叉过多、与背景重合的干扰（B1）
        const isHub = !isPaper && (n.degree || 0) >= 2
        const showLabel = isPaper || active || (isHub && !dimmed)
        if (showLabel) {
          const sprite = new SpriteText(n.short)
          sprite.color = dimmed ? '#5b6684' : isPaper ? '#dbe4ff' : '#cbd5e1'
          sprite.textHeight = isPaper ? 3.8 : 3.0
          sprite.position.set(0, -(r + (isPaper ? 6 : 4)), 0)
          // 子节点标签加深色圆角小底，和辉光/彼此分离，不糊成一片（B2）
          if (!isPaper) {
            sprite.backgroundColor = dimmed ? 'rgba(8,11,24,0.5)' : 'rgba(8,11,24,0.72)'
            sprite.padding = 1.2
            sprite.borderRadius = 2
          }
          group.add(sprite)
        }
        // 选中节点：在其周围「放电式」展开信息卡片（带动画）
        if (selected.value?.kind === 'node' && n.id === selected.value.id) {
          const entries = infoChipEntries()
          if (entries.length) {
            const wrap = new THREE.Group()
            const targets = []
            // 卡片是多行块，数量多时把半径推远、扇形张大，减少互相遮挡
            const R = r * 7 + entries.length * 2.5
            const spread = Math.PI * 1.3 // 右侧扇形展开角度范围
            const startA = -spread / 2
            entries.forEach((entry, i) => {
              const chip = makeChip(THREE, SpriteText, entry, n.color)
              const a = entries.length === 1 ? 0 : startA + (spread * i) / (entries.length - 1)
              targets.push(new THREE.Vector3(Math.cos(a) * R + r * 3, Math.sin(a) * R, 0))
              wrap.add(chip)
            })
            group.add(wrap)
            animateInfoIn(wrap, targets)
          }
        }
        return group
      })
      .linkCurvature(0.22) // 轴突：略带弯曲
      .linkColor((l) =>
        highlightNodes.size === 0 || highlightLinks.has(l._key) ? l.color : '#1b2240',
      )
      .linkWidth((l) => l.width)
      .linkOpacity(0.4)
      .linkDirectionalArrowLength(2.6)
      .linkDirectionalArrowRelPos(1)
      // 信号脉冲：默认安静，选中节点时相连轴突「放电」
      .linkDirectionalParticles((l) => (highlightLinks.has(l._key) ? 3 : 0))
      .linkDirectionalParticleSpeed(0.008)
      .linkDirectionalParticleWidth(1.8)
      .onNodeClick(on3dNodeClick)
      .onLinkClick(on3dLinkClick)
      .onBackgroundClick(clearSelection)
    rendered3dEl = container3d.value

    // 力参数：让网络铺成有机的「神经网」团块
    fg3d.d3Force('charge').strength(-90)
    fg3d.d3Force('link').distance((l) => (l.relation === 'cites' ? 55 : 80))

    // 静态氛围场：节点后方的彩色辉光团（生物场纵深感）
    addAmbientField(THREE)

    // 柔和辉光（降强度 + 提阈值：只让最亮的胞体核发光，不再整体过曝）
    const bloom = new UnrealBloomPass()
    bloom.strength = 0.6
    bloom.radius = 0.7
    bloom.threshold = 0.25
    fg3d.postProcessingComposer().addPass(bloom)

    // 极缓自转；选中时暂停，背景点击恢复
    controls3d = fg3d.controls()
    controls3d.autoRotate = true
    controls3d.autoRotateSpeed = 0.25

    // 尺寸同步：3d-force-graph@1.80 自身不监听 resize，实例创建后画布尺寸会「冻结」
    // 在初始容器宽高，导致放大/缩小窗口后画布不跟随、溢出并盖住右侧面板。
    // 用 ResizeObserver 盯住容器，尺寸有效（>0）时同步给 fg3d —— v-show 隐藏时为 0，跳过不误设。
    const syncSize3d = () => {
      const el = container3d.value
      if (!el) return
      const w = el.clientWidth
      const h = el.clientHeight
      if (w > 0 && h > 0) fg3d.width(w).height(h)
    }
    syncSize3d()
    ro3d?.disconnect()
    ro3d = new ResizeObserver(syncSize3d)
    ro3d.observe(container3d.value)
  }
  fg3d.graphData(data)
  // 稍等布局展开后自动取景
  setTimeout(() => fg3d && fg3d.zoomToFit(600, 60), 400)
}

// 选中某节点：设为选中项 + 高亮其子图 + 论文节点按需拉取结构化信息
function activateNode(rawNode) {
  selected.value = { kind: 'node', ...rawNode }
  updateHighlight(rawNode.id)
  if (controls3d) controls3d.autoRotate = false
  if (rawNode.type === 'paper') loadPaperInfo(rawNode.paper_id)
  else paperInfo.value = null
}

// 清空选中（背景点击）：取消高亮、恢复自转
function clearSelection() {
  selected.value = null
  paperInfo.value = null
  if (infoAnimRaf) {
    cancelAnimationFrame(infoAnimRaf)
    infoAnimRaf = null
  }
  updateHighlight(null)
  if (controls3d) controls3d.autoRotate = true
}

// 计算高亮集合（选中节点 + 直接邻居 + 相连边），并刷新 3D 视图外观
function updateHighlight(nodeId) {
  const hn = new Set()
  const hl = new Set()
  if (nodeId) {
    hn.add(nodeId)
    raw.value.edges.forEach((e, i) => {
      const key = edgeKey(e, i)
      if (hiddenEdges.value.has(key)) return
      if (e.source === nodeId || e.target === nodeId) {
        hn.add(e.source)
        hn.add(e.target)
        hl.add(key)
      }
    })
  }
  highlightNodes = hn
  highlightLinks = hl
  // 重新套用各访问器以重绘（含自定义 three 对象的明暗）
  if (viewMode.value === '3d' && fg3d) {
    fg3d
      .nodeColor(fg3d.nodeColor())
      .linkColor(fg3d.linkColor())
      .linkDirectionalParticles(fg3d.linkDirectionalParticles())
      .nodeThreeObject(fg3d.nodeThreeObject())
  }
}

// 论文节点：按需拉取结构化信息（Map 缓存，避免重复请求）
async function loadPaperInfo(paperId) {
  paperInfo.value = null
  if (!paperId) return
  if (paperInfoCache.has(paperId)) {
    paperInfo.value = paperInfoCache.get(paperId)
    refresh3dNodeObjects() // 信息已就绪，重建节点对象让卡片展开
    return
  }
  paperInfoLoading.value = true
  try {
    const res = await papersAPI.get(paperId)
    const info = res.structured_info || null
    paperInfoCache.set(paperId, info)
    // 仍停留在同一节点时才回填（避免拉取期间用户已切换）
    if (selected.value?.kind === 'node' && selected.value.paper_id === paperId) {
      paperInfo.value = info
      refresh3dNodeObjects() // 异步信息到达，重建节点对象让卡片展开
    }
  } catch {
    paperInfo.value = null
  } finally {
    paperInfoLoading.value = false
  }
}

// 飞行聚焦到点击的节点（灵动的镜头推进）
function on3dNodeClick(node) {
  const n = raw.value.nodes.find((x) => x.id === node.id)
  if (n) activateNode(n)
  const dist = 120
  const hyp = Math.hypot(node.x || 0, node.y || 0, node.z || 0) || 1
  const r = 1 + dist / hyp
  fg3d.cameraPosition(
    { x: (node.x || 0) * r, y: (node.y || 0) * r, z: (node.z || 0) * r },
    node,
    900,
  )
}
function on3dLinkClick(link) {
  const idx = raw.value.edges.findIndex((e, i) => edgeKey(e, i) === link._key)
  if (idx !== -1) {
    selected.value = { kind: 'edge', _key: link._key, ...raw.value.edges[idx] }
    paperInfo.value = null
  }
}

// 按当前视图模式渲染
function renderCurrentView() {
  if (viewMode.value === '3d') render3d()
  else renderNetwork()
}

async function switchView(mode) {
  if (viewMode.value === mode) return
  viewMode.value = mode
  await nextTick()
  if (raw.value.nodes.length) renderCurrentView()
}

// 当前选中节点的「相关节点」（由边推导：邻居 + 关系 + 方向），供详情面板展开
const relatedNodes = computed(() => {
  const sel = selected.value
  if (!sel || sel.kind !== 'node') return []
  const out = []
  const seen = new Set()
  raw.value.edges.forEach((e, i) => {
    const key = edgeKey(e, i)
    if (hiddenEdges.value.has(key)) return
    let otherId = null
    let dir = null
    if (e.source === sel.id) {
      otherId = e.target
      dir = 'out'
    } else if (e.target === sel.id) {
      otherId = e.source
      dir = 'in'
    } else {
      return
    }
    if (hiddenNodes.value.has(otherId)) return
    const node = raw.value.nodes.find((n) => n.id === otherId)
    if (!node) return
    const dedup = `${otherId}|${e.relation}|${dir}`
    if (seen.has(dedup)) return
    seen.add(dedup)
    out.push({ node, relation: e.relation, dir, key })
  })
  return out
})

// 数据集/方法节点：每篇使用它的论文 + 该论文里的原文片段（evidence），供侧栏「完整来源」展示
const usageEvidence = computed(() => {
  const sel = selected.value
  if (!sel || sel.kind !== 'node' || sel.type === 'paper') return []
  const out = []
  const seen = new Set()
  raw.value.edges.forEach((e, i) => {
    if (hiddenEdges.value.has(edgeKey(e, i))) return
    if (e.target !== sel.id) return // uses_* 边方向：论文 → 数据集/方法
    const paper = raw.value.nodes.find((n) => n.id === e.source && n.type === 'paper')
    if (!paper || seen.has(paper.id)) return
    seen.add(paper.id)
    out.push({ paper, evidence: e.evidence || '' })
  })
  return out
})

// 数据集/方法节点：使用它的论文列表（由 uses_* 边反推），供侧栏概要
const usedByPapers = computed(() => {
  const sel = selected.value
  if (!sel || sel.kind !== 'node' || sel.type === 'paper') return []
  const out = []
  const seen = new Set()
  raw.value.edges.forEach((e, i) => {
    if (hiddenEdges.value.has(edgeKey(e, i))) return
    if (e.target !== sel.id) return // uses_* 边方向：论文 → 数据集/方法
    const paper = raw.value.nodes.find((n) => n.id === e.source && n.type === 'paper')
    if (!paper || seen.has(paper.id)) return
    seen.add(paper.id)
    out.push(paper)
  })
  return out
})

// 点相关节点：切换选中并在当前视图里聚焦到它
function focusNode(node) {
  if (viewMode.value === '3d' && fg3d) {
    const target = fg3d.graphData().nodes.find((n) => n.id === node.id)
    if (target) {
      on3dNodeClick(target) // 内部会设置 selected 并飞行聚焦
      return
    }
  }
  activateNode(node)
  if (network) {
    network.selectNodes([node.id])
    network.focus(node.id, { scale: 1.2, animation: true })
  }
}

function onClick(params) {
  if (params.nodes && params.nodes.length) {
    const nid = params.nodes[0]
    const node = raw.value.nodes.find((n) => n.id === nid)
    if (node) activateNode(node)
    return
  }
  if (params.edges && params.edges.length) {
    const eid = params.edges[0]
    const idx = raw.value.edges.findIndex((e, i) => edgeKey(e, i) === eid)
    if (idx !== -1) {
      selected.value = { kind: 'edge', _key: eid, ...raw.value.edges[idx] }
      paperInfo.value = null
    }
    return
  }
  clearSelection()
}

// 过滤开关变化 → 重建当前视图
function applyFilters() {
  renderCurrentView()
}

// ---- 手动纠错（会话内） ----
function deleteSelected() {
  if (!selected.value) return
  if (selected.value.kind === 'node') {
    hiddenNodes.value = new Set(hiddenNodes.value).add(selected.value.id)
  } else {
    hiddenEdges.value = new Set(hiddenEdges.value).add(selected.value._key)
  }
  selected.value = null
  paperInfo.value = null
  highlightNodes = new Set()
  highlightLinks = new Set()
  renderCurrentView()
}

function openPaper() {
  if (selected.value?.kind === 'node' && selected.value.type === 'paper') {
    router.push(`/papers/${selected.value.paper_id}`)
  }
}

// 在新标签页打开论文详情（不打断当前图谱浏览）
function openPaperNewTab(paperId) {
  if (!paperId) return
  const href = router.resolve(`/papers/${paperId}`).href
  window.open(href, '_blank')
}

function refit() {
  if (viewMode.value === '3d') fg3d?.zoomToFit(600, 60)
  else network?.fit({ animation: true })
}

async function load() {
  if (!selectedPaperIds.value.size) {
    errorMsg.value = '请至少选择 1 篇论文'
    raw.value = { nodes: [], edges: [] }
    return
  }
  loading.value = true
  errorMsg.value = ''
  selected.value = null
  paperInfo.value = null
  highlightNodes = new Set()
  highlightLinks = new Set()
  hiddenNodes.value = new Set()
  hiddenEdges.value = new Set()
  try {
    // 全选时不传参（等价全部），否则传选中的 ID 列表
    const ids =
      selectedPaperIds.value.size === allPapers.value.length
        ? undefined
        : Array.from(selectedPaperIds.value)
    const res = await graphAPI.get(ids)
    raw.value = { nodes: res.nodes || [], edges: res.edges || [] }
    stats.value = res.stats || null
    llmUsed.value = !!res.llm_used
  } catch (err) {
    errorMsg.value = err.userMessage || '图谱加载失败，请重试'
  } finally {
    loading.value = false
  }
  // graph-body 是 v-else，loading=false 后才挂载，必须等它进 DOM 再渲染
  await nextTick()
  if (!errorMsg.value && raw.value.nodes.length) renderCurrentView()
}

// 拉取本人已解析论文作为可选范围
async function loadPaperList() {
  try {
    const res = await papersAPI.list({ status: 'completed', size: 100 })
    allPapers.value = res.items || []
    selectedPaperIds.value = new Set(allPapers.value.map((p) => p.paper_id))
  } catch {
    allPapers.value = []
  }
}

function togglePaper(id) {
  const next = new Set(selectedPaperIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  selectedPaperIds.value = next
}
function selectAllPapers() {
  selectedPaperIds.value = new Set(allPapers.value.map((p) => p.paper_id))
}
function clearPapers() {
  selectedPaperIds.value = new Set()
}
function applySelection() {
  showPicker.value = false
  load()
}

onMounted(async () => {
  await loadPaperList()
  // 从首页「图谱选择模式」带 ids 进来：直接按所选论文构图，不再弹选择面板
  const idsParam = (route.query.ids || '').toString().trim()
  if (idsParam) {
    const wanted = idsParam.split(',').map((s) => s.trim()).filter(Boolean)
    const valid = wanted.filter((id) => allPapers.value.some((p) => p.paper_id === id))
    if (valid.length) {
      selectedPaperIds.value = new Set(valid)
      load()
      return
    }
  }
  // 直接进入 /graph（无 ids）：展示「论文范围」选择面板，选定后点「生成图谱」再构图；
  // 无已解析论文时不打开面板，直接落到空态提示去上传/解析。
  showPicker.value = allPapers.value.length > 0
})
onBeforeUnmount(() => {
  if (infoAnimRaf) {
    cancelAnimationFrame(infoAnimRaf)
    infoAnimRaf = null
  }
  if (ambientRaf) {
    cancelAnimationFrame(ambientRaf)
    ambientRaf = null
  }
  if (network) {
    network.destroy()
    network = null
  }
  if (ro3d) {
    ro3d.disconnect()
    ro3d = null
  }
  if (fg3d) {
    fg3d._destructor?.()
    fg3d = null
  }
})
</script>

<template>
  <div class="graph-page">
    <header class="graph-header">
      <button class="back-btn" @click="router.push('/')">
        <ArrowLeft class="icon" />
        <span>返回</span>
      </button>
      <h1 class="graph-title">📊 知识图谱</h1>
      <div class="header-actions">
        <div class="view-toggle" title="2D / 3D 视图切换">
          <button :class="{ active: viewMode === '2d' }" @click="switchView('2d')">2D</button>
          <button :class="{ active: viewMode === '3d' }" @click="switchView('3d')">3D</button>
        </div>
        <button
          class="tool-btn picker-btn"
          :class="{ active: showPicker }"
          @click="showPicker = !showPicker"
          title="选择参与构图的论文"
        >
          <ListChecks class="icon-sm" />
          <span>论文范围（{{ selectedCount }}/{{ allPapers.length }}）</span>
        </button>
        <button class="tool-btn" @click="refit" title="重置视图" :disabled="!raw.nodes.length">
          <Maximize2 class="icon-sm" />
        </button>
        <button class="tool-btn" @click="load" title="重新加载" :disabled="loading">
          <RefreshCw class="icon-sm" :class="{ spinning: loading }" />
        </button>
      </div>

      <!-- 论文范围选择面板 -->
      <div v-if="showPicker" class="picker-panel">
        <div class="picker-head">
          <span>选择参与构图的论文</span>
          <div class="picker-head-actions">
            <button @click="selectAllPapers">全选</button>
            <button @click="clearPapers">清空</button>
          </div>
        </div>
        <div class="picker-list">
          <label v-for="p in allPapers" :key="p.paper_id" class="picker-item">
            <input
              type="checkbox"
              :checked="selectedPaperIds.has(p.paper_id)"
              @change="togglePaper(p.paper_id)"
            />
            <span class="picker-item-title">{{ p.title || p.file_name || '未命名论文' }}</span>
          </label>
          <p v-if="!allPapers.length" class="picker-empty">暂无已解析论文</p>
        </div>
        <button class="picker-apply" :disabled="!selectedCount" @click="applySelection">
          <Check class="icon-sm" />
          <span>生成图谱（{{ selectedCount }} 篇）</span>
        </button>
      </div>
    </header>

    <!-- 加载态 -->
    <div v-if="loading" class="state-box">
      <Loader2 class="spin" />
      <p>正在构建图谱…（首次分析可能较慢，之后走缓存会更快）</p>
    </div>

    <!-- 错误态 -->
    <div v-else-if="errorMsg" class="state-box">
      <p class="err">{{ errorMsg }}</p>
      <button class="retry-btn" @click="load">重试</button>
    </div>

    <!-- 空态 -->
    <div v-else-if="!raw.nodes.length" class="state-box">
      <Info class="info-icon" />
      <h2>暂无可展示的关系</h2>
      <p>需要至少几篇已解析论文，且论文间存在引用或共用数据集/方法时才会形成图谱。</p>
      <button class="retry-btn" @click="router.push('/')">去上传/解析论文</button>
    </div>

    <!-- 图谱主体 -->
    <div v-else class="graph-body">
      <div class="graph-canvas-wrap">
        <div v-if="paperCount < 3" class="soft-hint">
          提示：论文越多，图谱关系越丰富（建议 ≥3 篇）。
        </div>
        <div v-show="viewMode === '2d'" ref="container" class="graph-canvas"></div>
        <div v-show="viewMode === '3d'" ref="container3d" class="graph-canvas canvas-3d"></div>
        <div v-if="viewMode === '3d'" class="canvas-3d-vignette"></div>
        <div v-if="viewMode === '3d'" class="canvas-3d-hint">拖拽旋转 · 滚轮缩放 · 点击节点看详情</div>

        <!-- 图例 + 过滤 -->
        <div class="legend">
          <div class="legend-group">
            <span class="legend-item"><i class="dot paper"></i>论文</span>
            <span class="legend-item"><i class="dot dataset"></i>数据集</span>
            <span class="legend-item"><i class="dot method"></i>方法/模型</span>
          </div>
          <div class="legend-group filters">
            <label><input type="checkbox" v-model="filters.cites" @change="applyFilters" />引用</label>
            <label
              ><input type="checkbox" v-model="filters.uses_dataset" @change="applyFilters" />数据集</label
            >
            <label
              ><input type="checkbox" v-model="filters.uses_method" @change="applyFilters" />方法</label
            >
          </div>
        </div>
      </div>

      <!-- 详情 / 溯源侧栏 -->
      <aside class="side-panel">
        <div class="stats-card" v-if="stats">
          <div class="stats-row"><span>论文</span><strong>{{ stats.papers }}</strong></div>
          <div class="stats-row"><span>数据集</span><strong>{{ stats.datasets }}</strong></div>
          <div class="stats-row"><span>方法/模型</span><strong>{{ stats.methods }}</strong></div>
          <div class="stats-row"><span>引用边</span><strong>{{ stats.cites }}</strong></div>
          <div class="stats-note">
            {{ llmUsed ? 'AI 增强：实体由 LLM 抽取' : '未配置 API Key：规则匹配（可在设置页配置 Key 提升覆盖）' }}
          </div>
        </div>

        <div v-if="selected" class="detail-card">
          <template v-if="selected.kind === 'node'">
            <div class="detail-type">{{ TYPE_STYLE[selected.type]?.label || '节点' }}</div>
            <h3 class="detail-title">{{ selected.label }}</h3>
            <div v-if="selected.type === 'paper'" class="detail-meta">
              <span v-if="selected.field">领域：{{ selected.field }}</span>
              <span v-if="selected.read_status">状态：{{ selected.read_status }}</span>
            </div>
            <div v-if="selected.type !== 'paper'" class="entity-summary">
              该{{ selected.type === 'dataset' ? '数据集' : '方法/模型' }}被
              <strong>{{ usedByPapers.length }}</strong> 篇论文使用
            </div>
            <button v-if="selected.type === 'paper'" class="open-btn" @click="openPaper">
              打开论文详情
            </button>

            <!-- 数据集/方法：各论文中的完整用法原文（来源标注）+ 新标签打开论文 -->
            <div v-if="selected.type !== 'paper' && usageEvidence.length" class="usage-sources">
              <div class="usage-label">各论文中的用法（来源）</div>
              <div v-for="u in usageEvidence" :key="u.paper.id" class="usage-item">
                <div class="usage-paper">
                  <i class="dot paper"></i>
                  <span class="usage-paper-title" :title="u.paper.label">{{ u.paper.label }}</span>
                  <button
                    class="usage-open"
                    @click="openPaperNewTab(u.paper.paper_id)"
                    title="在新标签页打开论文"
                  >
                    打开 ↗
                  </button>
                </div>
                <p class="usage-evidence">
                  {{ u.evidence || '（论文中未提取到相关原文片段）' }}
                </p>
              </div>
            </div>

            <!-- 论文结构化信息：选中论文节点时按需拉取展示 -->
            <div v-if="selected.type === 'paper'" class="paper-info">
              <div v-if="paperInfoLoading" class="pi-loading">
                <Loader2 class="spin-sm" /><span>加载论文信息…</span>
              </div>
              <template v-else-if="paperInfo">
                <section v-if="paperInfo.research_background" class="pi-sec">
                  <h4>研究背景</h4>
                  <p>{{ paperInfo.research_background }}</p>
                </section>
                <section v-if="paperInfo.research_questions" class="pi-sec">
                  <h4>研究问题</h4>
                  <p>{{ paperInfo.research_questions }}</p>
                </section>
                <section v-if="paperInfo.method_flow" class="pi-sec">
                  <h4>方法流程</h4>
                  <p>{{ paperInfo.method_flow }}</p>
                </section>
                <section v-if="paperInfo.model_algorithm" class="pi-sec">
                  <h4>模型 / 算法</h4>
                  <p>{{ paperInfo.model_algorithm }}</p>
                </section>
                <section v-if="paperInfo.dataset_info" class="pi-sec">
                  <h4>数据集</h4>
                  <p>{{ paperInfo.dataset_info }}</p>
                </section>
                <section v-if="piList(paperInfo.innovations).length" class="pi-sec">
                  <h4>创新点</h4>
                  <ul>
                    <li v-for="(it, i) in piList(paperInfo.innovations)" :key="i">{{ it }}</li>
                  </ul>
                </section>
                <section v-if="piList(paperInfo.limitations).length" class="pi-sec">
                  <h4>局限性</h4>
                  <ul>
                    <li v-for="(it, i) in piList(paperInfo.limitations)" :key="i">{{ it }}</li>
                  </ul>
                </section>
              </template>
              <p v-else class="pi-empty">暂无结构化信息（可能尚未解析完成）。</p>
            </div>

            <div v-if="relatedNodes.length" class="related">
              <div class="related-label">相关节点（{{ relatedNodes.length }}）</div>
              <div class="related-list">
                <button
                  v-for="r in relatedNodes"
                  :key="r.key"
                  class="related-item"
                  :title="r.node.label"
                  @click="focusNode(r.node)"
                >
                  <i class="dot" :class="r.node.type"></i>
                  <span class="related-name">{{ r.node.label }}</span>
                  <span class="related-rel"
                    >{{ r.dir === 'out' ? '→' : '←' }}
                    {{ RELATION_LABEL[r.relation] || r.relation }}</span
                  >
                </button>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="detail-type">关系 · {{ RELATION_LABEL[selected.relation] || selected.relation }}</div>
            <div class="detail-conf">
              置信度：{{ selected.confidence }}
              <span v-if="selected.adjudicated_by" class="badge">{{
                selected.adjudicated_by === 'ai' ? 'AI 判定' : '规则匹配'
              }}</span>
            </div>
            <div class="detail-evidence">
              <div class="evidence-label">依据 / 溯源</div>
              <p>{{ selected.evidence || '（无）' }}</p>
            </div>
          </template>

          <button class="delete-btn" @click="deleteSelected">
            <Trash2 class="icon-sm" />
            <span>删除{{ selected.kind === 'node' ? '此节点' : '此关系' }}（仅本次）</span>
          </button>
        </div>

        <div v-else class="hint-card">
          <Info class="info-icon-sm" />
          <p>点击<strong>节点</strong>看详情 / 打开论文；点击<strong>边</strong>看关系溯源。发现错连可临时删除（刷新恢复）。</p>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.graph-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f8fafc;
}
.graph-header {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 24px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.picker-btn.active {
  border-color: #667eea;
  color: #4f46e5;
}
.picker-panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 24px;
  z-index: 30;
  width: 360px;
  max-height: 60vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
  overflow: hidden;
}
.picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid #f1f5f9;
  font-size: 0.9rem;
  font-weight: 600;
  color: #1f2937;
}
.picker-head-actions {
  display: flex;
  gap: 8px;
}
.picker-head-actions button {
  border: none;
  background: #f1f5f9;
  color: #4f46e5;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 0.78rem;
  cursor: pointer;
}
.picker-list {
  overflow-y: auto;
  padding: 6px;
}
.picker-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.86rem;
  color: #374151;
}
.picker-item:hover {
  background: #f8fafc;
}
.picker-item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.picker-empty {
  color: #9ca3af;
  font-size: 0.85rem;
  text-align: center;
  padding: 16px;
}
.picker-apply {
  margin: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: #667eea;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 10px;
  cursor: pointer;
  font-size: 0.9rem;
}
.picker-apply:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.graph-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #1f2937;
  margin: 0;
}
.header-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.back-btn,
.tool-btn,
.retry-btn,
.open-btn,
.delete-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  color: #374151;
  font-size: 0.9rem;
}
.back-btn:hover,
.tool-btn:hover {
  border-color: #667eea;
  color: #4f46e5;
}
.icon {
  width: 18px;
  height: 18px;
}
.icon-sm {
  width: 16px;
  height: 16px;
}
.spinning,
.spin {
  animation: spin 1s linear infinite;
}
.spin {
  width: 32px;
  height: 32px;
  color: #667eea;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.state-box {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #6b7280;
  text-align: center;
  padding: 24px;
}
.err {
  color: #dc2626;
}
.info-icon {
  width: 40px;
  height: 40px;
  color: #9ca3af;
}
.retry-btn {
  background: #667eea;
  color: #fff;
  border-color: transparent;
}

.graph-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.graph-canvas-wrap {
  flex: 1;
  position: relative;
  min-width: 0;
  overflow: hidden; /* 兜底：即使某帧画布尺寸暂时不匹配，也裁掉溢出、不盖住右侧面板 */
}
.graph-canvas {
  position: absolute;
  inset: 0;
}
.canvas-3d {
  background: #06070f;
}
/* 暗角：四周压暗、聚焦中心，烘托氛围（不拦截交互） */
.canvas-3d-vignette {
  position: absolute;
  inset: 0;
  z-index: 4;
  pointer-events: none;
  background: radial-gradient(
    ellipse 75% 75% at 50% 45%,
    rgba(6, 7, 15, 0) 55%,
    rgba(6, 7, 15, 0.55) 100%
  );
}
.canvas-3d-hint {
  position: absolute;
  bottom: 12px;
  left: 12px;
  z-index: 5;
  padding: 6px 12px;
  border-radius: 20px;
  background: rgba(15, 23, 42, 0.55);
  color: #cbd5e1;
  font-size: 0.78rem;
  backdrop-filter: blur(4px);
  pointer-events: none;
}
/* 2D / 3D 分段切换 */
.view-toggle {
  display: inline-flex;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
.view-toggle button {
  border: none;
  background: #fff;
  color: #6b7280;
  padding: 8px 14px;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.view-toggle button + button {
  border-left: 1px solid #e5e7eb;
}
.view-toggle button.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}
.soft-hint {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 5;
  background: #eef2ff;
  color: #4f46e5;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 0.8rem;
}
.legend {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 5;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 0.8rem;
  color: #374151;
}
.legend-group {
  display: flex;
  gap: 14px;
  align-items: center;
}
.legend-group.filters {
  border-top: 1px solid #f1f5f9;
  padding-top: 8px;
}
.legend-group.filters label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}
.dot.paper {
  background: #667eea;
}
.dot.dataset {
  background: #10b981;
  border-radius: 2px;
  transform: rotate(45deg);
}
.dot.method {
  background: #f59e0b;
  border-radius: 0;
  clip-path: polygon(50% 0, 100% 100%, 0 100%);
}

.side-panel {
  width: 300px;
  flex-shrink: 0;
  border-left: 1px solid #e5e7eb;
  background: #fff;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.stats-card {
  background: #f8fafc;
  border: 1px solid #eef2f7;
  border-radius: 10px;
  padding: 12px 14px;
}
.stats-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
  font-size: 0.9rem;
  color: #4b5563;
}
.stats-row strong {
  color: #1f2937;
}
.stats-note {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e5e7eb;
  font-size: 0.75rem;
  color: #9ca3af;
}
.detail-card,
.hint-card {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px;
}
.detail-type {
  font-size: 0.75rem;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.detail-title {
  margin: 6px 0 10px;
  font-size: 1rem;
  color: #1f2937;
  line-height: 1.4;
}
.detail-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
  color: #6b7280;
  margin-bottom: 12px;
}
.detail-conf {
  font-size: 0.9rem;
  color: #4b5563;
  margin-bottom: 10px;
}
.badge {
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4f46e5;
  font-size: 0.72rem;
}
.detail-evidence .evidence-label {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-bottom: 4px;
}
.detail-evidence p {
  font-size: 0.85rem;
  color: #374151;
  line-height: 1.5;
  background: #f8fafc;
  padding: 8px 10px;
  border-radius: 6px;
  word-break: break-word;
}
.open-btn {
  background: #667eea;
  color: #fff;
  border-color: transparent;
  width: 100%;
  justify-content: center;
}
.related {
  margin-top: 14px;
}
.related-label {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-bottom: 6px;
}
.related-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 220px;
  overflow-y: auto;
}
.related-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  border: 1px solid #eef2f7;
  background: #f8fafc;
  border-radius: 8px;
  padding: 7px 10px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.related-item:hover {
  border-color: #667eea;
  background: #eef2ff;
}
.related-item .dot {
  flex-shrink: 0;
}
.related-name {
  flex: 1;
  min-width: 0;
  font-size: 0.83rem;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.related-rel {
  flex-shrink: 0;
  font-size: 0.72rem;
  color: #6b7280;
}
/* 论文结构化信息卡 */
.paper-info {
  margin-top: 14px;
  border-top: 1px dashed #e5e7eb;
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.pi-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-size: 0.85rem;
}
.spin-sm {
  width: 16px;
  height: 16px;
  color: #667eea;
  animation: spin 1s linear infinite;
}
.pi-sec h4 {
  margin: 0 0 4px;
  font-size: 0.78rem;
  color: #4f46e5;
  font-weight: 700;
}
.pi-sec p {
  margin: 0;
  font-size: 0.83rem;
  line-height: 1.55;
  color: #374151;
  white-space: pre-wrap;
  word-break: break-word;
}
.pi-sec ul {
  margin: 0;
  padding-left: 18px;
}
.pi-sec li {
  font-size: 0.83rem;
  line-height: 1.5;
  color: #374151;
}
.pi-empty {
  font-size: 0.83rem;
  color: #9ca3af;
}
.entity-summary {
  font-size: 0.9rem;
  color: #4b5563;
  margin-bottom: 12px;
}
/* 数据集/方法：各论文用法原文（来源） */
.usage-sources {
  margin-top: 14px;
  border-top: 1px dashed #e5e7eb;
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.usage-label {
  font-size: 0.75rem;
  color: #9ca3af;
}
.usage-item {
  border: 1px solid #eef2f7;
  border-radius: 8px;
  background: #f8fafc;
  padding: 8px 10px;
}
.usage-paper {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.usage-paper-title {
  flex: 1;
  min-width: 0;
  font-size: 0.82rem;
  font-weight: 600;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.usage-open {
  flex-shrink: 0;
  border: 1px solid #e5e7eb;
  background: #fff;
  color: #4f46e5;
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 0.72rem;
  cursor: pointer;
}
.usage-open:hover {
  border-color: #667eea;
  background: #eef2ff;
}
.usage-evidence {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.55;
  color: #4b5563;
  white-space: pre-wrap;
  word-break: break-word;
}
.entity-summary strong {
  color: #4f46e5;
  font-size: 1.05rem;
}
.delete-btn {
  margin-top: 12px;
  width: 100%;
  justify-content: center;
  color: #dc2626;
  border-color: #fecaca;
}
.delete-btn:hover {
  background: #fef2f2;
}
.hint-card {
  display: flex;
  gap: 10px;
  color: #6b7280;
  font-size: 0.85rem;
  line-height: 1.5;
  background: #f8fafc;
}
.info-icon-sm {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  color: #9ca3af;
}
</style>
