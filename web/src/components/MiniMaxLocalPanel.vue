<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({ api: { type: Function, required: true } })
const emit = defineEmits(['navigate'])
const status = ref(null)
const projects = ref([])
const history = ref([])
const selected = ref(null)
const busy = ref(false)
const uploading = ref(false)
const error = ref('')
const form = reactive({ projectId: null, inputImagePath: '', seed: 2026101801, prompt: '', profile: 'baseline480', steps: 20 })
const profiles = computed(() => status.value?.generationProfiles || [{ id: 'baseline480', label: '480p 基线', width: 864, height: 480, workflowId: status.value?.workflowId }])
const selectedProfile = computed(() => profiles.value.find(p => p.id === form.profile))
let requestKey = crypto.randomUUID()
let polling = false
let poller
let disposed = false
let selectionVersion = 0
watch(form, () => { requestKey = crypto.randomUUID() }, { deep: true })
watch(() => form.projectId, () => { form.inputImagePath = '' })
watch(() => form.profile, profile => { if (profile !== 'native1080') form.steps = 20 })
const progress = computed(() => status.value?.totalBytes ? Math.min(100, Math.floor(status.value.downloadedBytes * 100 / status.value.totalBytes)) : 0)
const canSubmit = computed(() => status.value?.modelsPresent && selectedProfile.value?.workflowId && status.value?.comfyOnline
  && status.value?.queue?.enabled && !status.value?.queue?.paused && form.projectId && form.inputImagePath && form.prompt.trim() && !busy.value && !uploading.value)
function mediaUrl(result) {
  if (result.mediaUrl) return result.mediaUrl
  const path = result.assetPath || result.relativePath || result.path
  return path ? `/api/media?assetPath=${encodeURIComponent(path)}` : ''
}
function isVideo(result) { return /\.(mp4|webm)$/i.test(result.assetPath || result.relativePath || result.path || '') }
function isAudio(result) { return /\.(wav|mp3|flac|ogg)$/i.test(result.assetPath || result.relativePath || result.path || '') }
function isImage(result) { return /\.(png|jpe?g|webp)$/i.test(result.assetPath || result.relativePath || result.path || '') }
function gib(bytes) { return ((bytes || 0) / 1024 ** 3).toFixed(2) }
const runStage = computed(() => ({ CreatingProject: '创建验收项目', GeneratingKeyframe: '生成全新首帧', GeneratingBaseline: '验证原有 LTX 路线', GeneratingLocalTts: '验证原有本地配音', WaitingForModels: '等待 H3 模型下载', VerifyingModels: '核对 H3 模型哈希', GeneratingH3: '生成 H3 声画短片', AwaitingContentReview: '技术生成完成，等待人工内容审核', Blocked: '验收需要处理', Failed: '验收失败' })[status.value?.integrationRun?.stage] || status.value?.integrationRun?.stage)
async function load() {
  if (polling || disposed) return
  polling = true
  try {
    const responses = await Promise.allSettled([props.api('/api/minimax/local/status'), props.api('/api/minimax/local/history')])
    if (disposed) return
    const failures = []
    if (responses[0].status === 'fulfilled') status.value = responses[0].value
    else failures.push(responses[0].reason.message)
    if (responses[1].status === 'fulfilled') history.value = responses[1].value
    else failures.push(responses[1].reason.message)
    error.value = failures.join('；')
    if (selected.value && ['Pending', 'Running'].includes(selected.value.task.status)) await selectTask(selected.value.task.id)
  } finally { polling = false }
}
async function selectTask(id) {
  const version = ++selectionVersion
  try {
    const detail = await props.api(`/api/tasks/${id}`)
    if (!disposed && version === selectionVersion) selected.value = detail
  } catch (failure) { if (!disposed) error.value = failure.message }
}
async function prepare() {
  busy.value = true
  try {
    await props.api('/api/minimax/local/register', { method: 'POST' })
    await props.api('/api/minimax/local/verify', { method: 'POST' })
    ElMessage.success('本地模型与工作流已校验')
    await load()
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
async function upload(event) {
  const file = event.target.files?.[0]
  if (!file || !form.projectId) return
  uploading.value = true
  const projectAtUpload = form.projectId
  const data = new FormData()
  data.append('projectId', projectAtUpload)
  data.append('file', file)
  try {
    const result = await props.api('/api/minimax/local/reference', { method: 'POST', headers: {}, body: data })
    if (form.projectId === projectAtUpload) form.inputImagePath = result.assetPath
  } catch (failure) { error.value = failure.message }
  finally { uploading.value = false; event.target.value = '' }
}
async function submit() {
  if (!canSubmit.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await props.api('/api/minimax/local/video', { method: 'POST', headers: { 'Idempotency-Key': requestKey }, body: JSON.stringify(form) })
    await selectTask(result.id)
    await load()
    ElMessage.success(`本地生成任务 ${result.id} 已加入队列`)
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
async function cancelTask(id) {
  try { await props.api(`/api/tasks/${id}/cancel`, { method: 'POST' }); await load() }
  catch (failure) { error.value = failure.message }
}
onMounted(async () => {
  try { projects.value = await props.api('/api/projects') } catch (failure) { error.value = failure.message }
  await load()
  if (!disposed) poller = setInterval(load, 10000)
})
onBeforeUnmount(() => { disposed = true; clearInterval(poller) })
</script>

<template>
  <section class="page-content minimax-page">
    <div class="toolbar">
      <div><div class="eyebrow">MiniMax H3 · 本地生成</div><h2>先做一条有声音的短片</h2><p class="muted">使用本机显卡，无需 API Key。现有本地生成仍在项目制作与声音页面。</p></div>
      <el-button plain @click="load">刷新状态</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <div v-if="status?.integrationRun" class="panel">
      <div class="panel-head"><h3>接入验收进度</h3><el-tag :type="status.integrationRun.stage === 'AwaitingContentReview' ? 'success' : 'info'">{{ runStage }}</el-tag></div>
      <p class="muted">新生成首帧和基线素材；内容通过与发布资格仍需单独审核。</p>
      <p v-if="status.integrationRun.error" class="minimax-error">{{ status.integrationRun.error }}</p>
      <el-button v-if="status.integrationRun.keyframeTaskId" plain @click="selectTask(status.integrationRun.keyframeTaskId)">查看新首帧任务</el-button>
      <el-button v-if="status.integrationRun.baselineV2TaskId || status.integrationRun.baselineTaskId" plain @click="selectTask(status.integrationRun.baselineV2TaskId || status.integrationRun.baselineTaskId)">查看本地基线</el-button>
      <el-button v-if="status.integrationRun.h3TaskId" type="primary" plain @click="selectTask(status.integrationRun.h3TaskId)">查看 H3 结果</el-button>
    </div>
    <div class="panel minimax-readiness">
      <div class="panel-head"><h3>本地模型准备</h3><el-tag :type="status?.modelsVerified ? 'success' : 'warning'">{{ status?.modelsVerified ? '已核对模型' : status?.modelsPresent ? '等待哈希校验' : '模型未就绪' }}</el-tag></div>
      <p class="muted">已下载 {{ gib(status?.downloadedBytes) }} / {{ gib(status?.totalBytes) }} GiB。下载进度按实际完成的数据块计算。</p>
      <el-progress :percentage="progress" :status="status?.modelsPresent ? 'success' : undefined" />
      <div class="minimax-components"><div v-for="asset in status?.assets || []" :key="asset.role"><strong>{{ asset.file }}</strong><span>{{ gib(asset.downloadedBytes) }} / {{ gib(asset.expectedBytes) }} GiB · {{ asset.verified ? '已校验' : asset.present ? '待校验' : '未完成' }}</span></div></div>
      <el-button :loading="busy" :disabled="!status?.modelsPresent" @click="prepare">校验并准备本地生成</el-button>
      <p v-if="status && !status.comfyOnline" class="muted">ComfyUI 当前离线，请先启动本地生成服务。</p>
      <p v-if="status && !status.queue.enabled" class="muted">后台生成队列尚未启用；准备完成后需要启动生成 Worker。</p>
    </div>
    <div class="two-col">
      <div class="panel">
        <div class="panel-head"><h3>镜头与声音</h3><el-tag type="info">约 5.17 秒 · 实验</el-tag></div>
        <el-form label-position="top">
          <el-form-item label="素材归属项目"><el-select v-model="form.projectId" placeholder="选择项目"><el-option v-for="project in projects" :key="project.id" :value="project.id" :label="project.name" /></el-select></el-form-item>
          <el-form-item label="生成规格"><el-select v-model="form.profile" aria-label="H3 生成规格"><el-option v-for="profile in profiles" :key="profile.id" :value="profile.id" :label="`${profile.label} · ${profile.width}×${profile.height}`" :disabled="!profile.workflowId" /></el-select></el-form-item>
          <p v-if="form.profile === 'quality768'" class="muted">768p为独立画质实验，占用更多资源；失败时保留原因，不自动降为480p。</p>
          <p v-if="form.profile === 'native1080'" class="muted">原生1920×1088实验，工作流上下各裁4行输出1920×1080。需要更多显存、内存和时间，本机已完成一次5秒短片技术验证，画质与运动效果仍需人工复核。</p>
          <el-form-item label="本镜头的首帧"><input aria-label="上传 MiniMax 首帧" type="file" accept="image/png,image/jpeg,image/webp" :disabled="!form.projectId || uploading" @change="upload" /><img v-if="form.inputImagePath" :src="mediaUrl({ assetPath: form.inputImagePath })" alt="当前首帧" class="minimax-reference" /></el-form-item>
          <el-form-item label="画面、动作与声音描述"><el-input v-model="form.prompt" type="textarea" :rows="6" maxlength="7000" show-word-limit placeholder="描述一个能在短片内完成的动作。需要对白时明确人物、台词、语气；不需要对白时写明环境声、无对白。" /></el-form-item>
          <el-form-item label="固定种子"><el-input-number v-model="form.seed" :min="0" :max="2147483647" :precision="0" /></el-form-item>
          <el-form-item v-if="form.profile === 'native1080'" label="采样步数"><el-select v-model="form.steps" aria-label="H3 采样步数"><el-option :value="20" label="20步 · 原有路线" /><el-option :value="30" label="30步 · 同首帧画质对照" /></el-select></el-form-item>
          <p class="muted">{{ selectedProfile?.width }}×{{ selectedProfile?.height }}、24 FPS、{{ form.steps }}步。每次保留视频、原生音轨与参数记录，人工审核后再决定是否采用。</p>
          <el-button type="primary" :loading="busy" :disabled="!canSubmit" @click="submit">生成视频与声音</el-button>
          <el-button plain @click="emit('navigate', 'voice')">独立配音</el-button>
        </el-form>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>本次结果</h3><el-tag type="warning">等待内容审核</el-tag></div>
        <template v-if="selected">
          <p>任务 #{{ selected.task.id }} · {{ selected.task.status }}</p>
          <p v-if="selected.task.errorMessage" class="minimax-error">{{ selected.task.errorMessage }}</p>
          <el-progress v-if="['Pending', 'Running'].includes(selected.task.status)" :percentage="Math.floor((selected.task.progress || 0) * 100)" />
          <template v-for="result in selected.results || []" :key="result.id">
            <img v-if="isImage(result)" :src="mediaUrl(result)" alt="新生成的验收首帧" class="minimax-preview" />
            <video v-if="isVideo(result)" controls preload="metadata" :src="mediaUrl(result)" class="minimax-preview" />
            <div v-if="isAudio(result)" class="minimax-audio"><p>独立原生音轨</p><audio controls preload="metadata" :src="mediaUrl(result)" /><a :href="mediaUrl(result)" download>下载音轨</a></div>
          </template>
          <el-button v-if="['Pending', 'Running'].includes(selected.task.status)" type="warning" plain @click="cancelTask(selected.task.id)">取消本次生成</el-button>
        </template>
        <el-empty v-else description="生成后在这里预览视频和试听音轨" />
      </div>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>最近实验版本</h3><span class="muted">每次任务单独保存，点击查看；完成状态不代表内容已通过审核。</span></div>
      <el-table :data="history" class="dark-table" @row-click="row => selectTask(row.id)"><el-table-column prop="id" label="任务" width="90" /><el-table-column prop="provider" label="生成路线" /><el-table-column prop="profile" label="规格" /><el-table-column prop="seed" label="种子" /><el-table-column prop="status" label="执行状态" /><el-table-column prop="createdAt" label="创建时间" min-width="170" /></el-table>
    </div>
  </section>
</template>

<style scoped>
.minimax-page { display: grid; gap: 18px; }
.minimax-components { display: grid; gap: 10px; margin: 18px 0; }
.minimax-components > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; font-size: 12px; }
.minimax-components strong { overflow-wrap: anywhere; font-weight: 500; }
.minimax-components span { color: #94a6bf; }
.minimax-reference { display: block; max-height: 180px; max-width: 100%; margin-top: 12px; border-radius: 8px; }
.minimax-preview { display: block; width: 100%; margin: 12px 0; border-radius: 8px; }
.minimax-audio audio { width: 100%; }
.minimax-audio a { display: inline-block; color: #88d5ff; margin: 10px 0; }
.minimax-error { color: #ffb4a9; overflow-wrap: anywhere; }
.minimax-page .el-select { width: 100%; }
.minimax-page .el-input-number { width: 220px; }
@media (max-width: 900px) { .minimax-page .two-col { grid-template-columns: 1fr; } }
</style>
