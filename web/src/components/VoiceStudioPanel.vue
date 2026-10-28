<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const props = defineProps({ api: { type: Function, required: true } })
const emit = defineEmits(['task-created'])
const catalog = ref({ voices: [], qwenAvailable: false })
const projects = ref([])
const history = ref([])
const task = ref(null)
const audio = ref(null)
const inference = ref(null)
const error = ref('')
const submitting = ref(false)
const engine = ref('Qwen3TTS')
const form = reactive({ projectId: null, voiceId: 'qwen3:Vivian', text: '午后的阳光穿过树叶，落在安静的校园里。林夏拾起长椅上的红色笔记本，轻声喊道：同学，你的本子忘拿了。', instruction: '用温柔、自然的普通话讲述，语速稍慢，句间停顿清晰，像在讲一个校园故事。', speed: 1, pitch: 0 })
const isQwen = computed(() => engine.value === 'Qwen3TTS')
const voices = computed(() => catalog.value.voices.filter(v => v.engine === engine.value))
const recent = computed(() => history.value.filter(t => isQwen.value ? t.resourceClass === 'GPU' : t.resourceClass !== 'GPU'))
const pending = computed(() => ['Pending', 'Running', 'Retrying'].includes(task.value?.status))
const statusLabel = computed(() => ({ Pending: '等待生成', Running: '正在配音', Succeeded: '配音已生成', Failed: '生成失败', Cancelled: '已取消' })[task.value?.status] || '')
let disposed = false
let timer
let selection = 0

watch(engine, () => {
  form.voiceId = voices.value.find(v => v.id === 'qwen3:Vivian')?.id || voices.value[0]?.id || ''
  form.speed = 1; form.pitch = 0
  clearTimeout(timer); selection++; task.value = null; audio.value = null; inference.value = null
  if (recent.value[0]) selectTask(recent.value[0].id)
})

async function refresh() {
  try {
    const [voiceData, projectData, taskData] = await Promise.all([props.api('/api/audio/voices'), props.api('/api/projects'), props.api('/api/audio/history?limit=100')])
    if (disposed) return
    catalog.value = voiceData
    projects.value = projectData
    if (!form.projectId) form.projectId = projectData[0]?.id || null
    history.value = taskData.filter(t => ['Audio', 'TTS'].includes(t.taskType)).slice(0, 8)
    if (!task.value && recent.value[0]) await selectTask(recent.value[0].id)
  } catch (e) { error.value = e.message }
}

async function poll(id, version) {
  try {
    const detail = await props.api(`/api/tasks/${id}`)
    if (disposed || version !== selection) return
    task.value = detail.task
    audio.value = detail.results.find(r => r.available && (r.mimeType?.startsWith('audio/') || r.assetPath?.toLowerCase().endsWith('.wav'))) || null
    const receipt = detail.results.find(r => r.available && r.assetPath?.endsWith('.json'))
    if (receipt) {
      const metadata = await props.api(receipt.mediaUrl)
      if (!disposed && version === selection) inference.value = metadata
    }
    if (pending.value) timer = setTimeout(() => poll(id, version), 1800)
    else if (detail.task.status === 'Failed') error.value = detail.task.errorMessage || '配音任务失败，可在任务中心查看详情。'
  } catch (e) {
    if (disposed || version !== selection) return
    error.value = `暂时无法读取任务：${e.message}。稍后刷新查看已有任务。`
  }
}

async function selectTask(id) {
  clearTimeout(timer)
  error.value = ''
  audio.value = null
  inference.value = null
  await poll(id, ++selection)
}

async function generate() {
  if (submitting.value || pending.value) return
  error.value = ''
  if (!form.projectId || !form.text.trim()) { error.value = '请选择保存项目并填写配音文本。'; return }
  submitting.value = true
  try {
    const body = { ...form, instruction: isQwen.value ? form.instruction : '' }
    const result = await props.api('/api/audio/tts', { method: 'POST', body: JSON.stringify(body) })
    emit('task-created')
    await selectTask(result.taskId)
    const rows = await props.api('/api/audio/history?limit=100')
    history.value = rows.filter(t => ['Audio', 'TTS'].includes(t.taskType)).slice(0, 8)
  } catch (e) { error.value = e.message }
  finally { submitting.value = false }
}

onMounted(refresh)
onBeforeUnmount(() => { disposed = true; selection++; clearTimeout(timer) })
</script>

<template>
  <section class="page-content voice-studio">
    <div class="toolbar"><div><div class="eyebrow">声音 / 本地配音</div><h2>声音工作台</h2></div><el-button plain @click="refresh">刷新音色与任务</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <div class="two-col">
      <div class="panel">
        <div class="panel-head"><h3>中文配音</h3><el-tag :type="catalog.qwenAvailable ? 'success' : 'warning'">{{ catalog.qwenAvailable ? 'Qwen3-TTS 本地就绪' : 'Qwen3-TTS 尚未就绪' }}</el-tag></div>
        <el-form label-position="top" :disabled="submitting || pending">
          <div class="form-row">
            <el-form-item label="配音引擎"><el-select v-model="engine" aria-label="配音引擎"><el-option label="Qwen3-TTS 本地" value="Qwen3TTS"/><el-option label="Windows 系统语音" value="Windows"/></el-select></el-form-item>
            <el-form-item label="音色"><el-select v-model="form.voiceId" aria-label="音色"><el-option v-for="v in voices" :key="v.id" :label="v.name" :value="v.id"/></el-select></el-form-item>
          </div>
          <el-form-item label="保存到项目"><el-select v-model="form.projectId" aria-label="保存到项目" filterable placeholder="选择项目"><el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id"/></el-select></el-form-item>
          <el-form-item label="配音文本"><el-input v-model="form.text" aria-label="配音文本" type="textarea" :rows="6" :maxlength="isQwen ? 500 : 3000" show-word-limit /></el-form-item>
          <el-form-item v-if="isQwen" label="演绎指令"><el-input v-model="form.instruction" aria-label="演绎指令" type="textarea" :rows="3" :maxlength="300" show-word-limit placeholder="例如：平静讲述，语速稍慢；后半句带一点惊喜。"/></el-form-item>
          <div v-else class="form-row"><el-form-item label="语速"><el-input-number v-model="form.speed" :min="0.5" :max="2" :step="0.1"/></el-form-item></div>
          <el-button type="primary" :loading="submitting" :disabled="pending || (isQwen && !catalog.qwenAvailable)" @click="generate">{{ pending ? '配音任务进行中' : '生成中文配音' }}</el-button>
        </el-form>
        <p v-if="isQwen" class="muted">通过演绎指令控制语气、情绪和语速。配音完成后释放显存，长文本请按段生成。</p>
        <p v-if="isQwen && !catalog.qwenAvailable" class="muted">{{ catalog.qwenMessage }}</p>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>试听</h3><el-tag v-if="task" :type="task.status === 'Succeeded' ? 'success' : 'info'">{{ statusLabel }}</el-tag></div>
        <template v-if="audio">
          <audio :key="audio.mediaUrl" controls preload="metadata" :src="audio.mediaUrl" aria-label="中文配音试听" />
          <p>{{ Number(audio.durationSeconds || 0).toFixed(1) }} 秒 · WAV</p>
          <p v-if="inference">Qwen3-TTS · {{ inference.voice }}<span v-if="inference.cacheHit"> · 已复用配音</span></p>
          <a :href="audio.mediaUrl" download>下载配音</a>
          <p class="muted">请试听确认发音、情绪和节奏，再用于成片。</p>
        </template>
        <p v-else class="muted">{{ pending ? '任务已保存，完成后可在这里试听。' : '生成完成后在这里播放。' }}</p>
        <p v-if="task" class="muted">任务 {{ task.id }} <span v-if="task.durationMs"> · 耗时 {{ (task.durationMs / 1000).toFixed(1) }} 秒</span></p>
        <div v-if="recent.length" class="voice-history"><h4>最近配音</h4><el-button v-for="item in recent" :key="item.id" plain :disabled="pending" @click="selectTask(item.id)">任务 {{ item.id }}</el-button></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.voice-studio .el-alert { margin-bottom: 18px; }
.voice-studio .el-select, .voice-studio audio { width: 100%; }
.voice-history { margin-top: 28px; }
.voice-history .el-button { margin: 4px; }
</style>
