<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MiniMaxLocalPanel from './components/MiniMaxLocalPanel.vue'
import VoiceStudioPanel from './components/VoiceStudioPanel.vue'
import CharacterLibraryPanel from './components/CharacterLibraryPanel.vue'
import CharacterStoryPanel from './components/CharacterStoryPanel.vue'

const active = ref('dashboard')
const loading = ref(false)
const errorText = ref('')
const authReady = ref(false)
const authBusy = ref(false)
const authError = ref('')
const auth = reactive({ configured: false, authenticated: false, setupAllowed: false, loginRequired: true, accessMode: 'Password', username: '', role: '', csrfToken: '', expiresAt: null })
const workbenchAvailable = computed(() => authReady.value && (!auth.loginRequired || auth.authenticated))
const authForm = reactive({ username: '', password: '', confirmPassword: '' })
const health = ref(null)
const settings = ref(null)
const dashboard = reactive({ counts: {}, recentTasks: [], comfy: null })
const projects = ref([])
const characters = ref([])
const scenes = ref([])
const workflows = ref([])
const workflowContracts = ref(null)
const models = ref([])
const presets = ref([])
const tasks = ref([])
const assets = ref([])
const scripts = ref([])
const selectedScript = ref(null)
const analysisResult = ref(null)
const productionStatus = ref(null)
const selectedProject = ref(null)
const episodes = ref([])
const shots = ref([])
const selectedEpisode = ref(null)
const episodeOutput = ref(null)
const episodeOutputLoading = ref(false)
const episodeOutputDialog = ref(false)
const selectedEpisodeOutputTaskId = ref(null)
let episodeOutputPoller = null
let projectSelectionVersion = 0
let episodeSelectionVersion = 0
const candidateDialog = ref(false)
const candidateShot = ref(null)
const candidateOptions = ref([])
const candidateLoading = ref(false)
const qaEpisodes = ref([])
const qaSelectedEpisode = ref(null)
const qaDetail = ref(null)
const qaPreset = ref('Standard')
const releaseCandidates = ref([])
const releaseCandidatesLoading = ref(false)
const releaseCandidatesError = ref('')
const releaseCandidateDialog = ref(false)
const releaseCandidateCreating = ref(false)
const releaseCandidateRequestKey = ref('')
const releaseExportDialog = ref(false)
const releaseExporting = ref(false)
const releaseExportCandidateId = ref(null)
const releaseCandidateForm = reactive({ licenseEvidenceConfirmed: false, licenseReference: '', licenseScope: '', licenseModels: '', assetVersionBinding: '', licenseTerritory: '', licensePlatforms: '', aiDisclosureRecorded: false, aiDisclosure: '', aiDisclosurePath: '', note: '' })
const characterReviewDialog = ref(false)
const characterReviewTarget = ref(null)
const characterReferences = ref([])
const characterReferencesLoading = ref(false)
const referenceUploadDialog = ref(false)
const referenceUploadMeta = reactive({ stage: 'base', role: 'identity', changeReason: '' })
const takeDialog = ref(false)
const takeShot = ref(null)
const takeOptions = ref([])
const takesLoading = ref(false)

const projectDialog = ref(false)
const episodeDialog = ref(false)
const shotDialog = ref(false)
const characterDialog = ref(false)
const sceneDialog = ref(false)
const scriptDialog = ref(false)
const projectForm = reactive({ id: null, name: '', description: '', status: 'Active', aspectRatio: '16:9', style: '', defaultFps: 30, defaultWidth: 1920, defaultHeight: 1080, promptStyle: '', bgmPath: '', bgmVolume: 0.18 })
const episodeForm = reactive({ id: null, projectId: null, episodeNumber: 1, name: '', description: '', targetSeconds: 60, outputFps: 30, outputWidth: 1920, outputHeight: 1080 })
const shotForm = reactive({ id: null, projectId: null, episodeId: null, shotNumber: 1, title: '', sceneId: null, characterIds: [], prompt: '', negativePrompt: '', workflowId: null, seed: null, width: 512, height: 320, frames: 121, fps: 24, inputImagePath: '', motionPreset: '电影感慢动作', cameraPreset: '中景', status: 'Draft' })
const characterForm = reactive({ id: null, projectId: null, name: '', ageSetting: '', faceFeatures: '', hair: '', clothes: '', bodyRatio: '', fixedPrompt: '', negativePrompt: '', anchorPath: '', voiceId: '', voiceSpeed: 1, voicePitch: 0 })
const sceneForm = reactive({ id: null, projectId: null, name: '', description: '', fixedPrompt: '', negativePrompt: '', style: '', anchorPath: '' })
const scriptForm = reactive({ id: null, projectId: null, episodeId: null, title: '', content: '', language: 'zh-CN', status: 'Draft' })
const referenceFile = ref(null)
const referenceTarget = ref(null)

const navItems = [
  { id: 'dashboard', label: '总览', icon: '⌂', hint: '运行状态与最近任务' },
  { id: 'projects', label: '项目制作', icon: '▣', hint: '剧集、镜头与批量生成' },
  { id: 'characters', label: '角色资产', icon: '◎', hint: '身份锚点与参考图' },
  { id: 'character-library', label: '人物参考库', icon: '◉', hint: '人物设定、参考图与不可变造型版本' },
  { id: 'character-story', label: '剧情选角与试片', icon: '◈', hint: '项目选角、分镜绑定、关键帧检查与H3送审预览' },
  { id: 'scenes', label: '场景资产', icon: '◇', hint: '场景主图与固定提示词' },
  { id: 'scripts', label: '剧本拆分', icon: '✎', hint: '剧本、人物/场景识别与分镜' },
  { id: 'production', label: '生产中心', icon: '▶', hint: '关键帧、视频、QC 与合成' },
  { id: 'minimax', label: 'MiniMax 本地', icon: '◉', hint: '开源 H3 视频与原生声音实验' },
  { id: 'qa', label: '质量验收', icon: '✓', hint: '技术、镜头与 Episode 发布验收' },
  { id: 'voice', label: '声音', icon: '♫', hint: '本地 TTS、旁白与对白' },
  { id: 'sfx', label: '音效 / BGM', icon: '◈', hint: '本地音效库与背景音乐' },
  { id: 'tasks', label: '任务中心', icon: '↯', hint: '队列、重试、取消与历史' },
  { id: 'assets', label: '素材中心', icon: '▤', hint: '图片、视频、音频与输出' },
  { id: 'workflows', label: '工作流与模型', icon: '⌘', hint: '扫描 ComfyUI 工作流' },
  { id: 'system', label: '系统设置', icon: '⚙', hint: '路径、GPU 与连接诊断' }
]

const currentNav = computed(() => navItems.find(x => x.id === active.value) || navItems[0])
const initialNav = typeof window !== 'undefined' ? window.location.hash.slice(1) : ''
if (navItems.some(item => item.id === initialNav)) active.value = initialNav
if (typeof window !== 'undefined' && !window.location.hash) window.history.replaceState(null, '', '#dashboard')
const videoWorkflows = computed(() => workflows.value.filter(workflow => {
  const type = String(workflow.workflowType || '').toLowerCase()
  return ['imagetovideo', 'i2v', 'video'].includes(type) && /\.json$/i.test(workflow.path || '')
}))
const episodeOutputVersions = computed(() => episodeOutput.value?.versions || [])
const readyReleaseCandidates = computed(() => releaseCandidates.value.filter(candidate => String(candidate.status || '').toLowerCase() === 'ready' && String(candidate.releaseEligibility || '').toLowerCase() === 'ready'))
const latestEpisodeOutputVersion = computed(() => {
  const output = episodeOutput.value
  const version = output?.latestVersion || episodeOutputVersions.value.find(item => item.status === 'Succeeded' && item.exists)
  return version || (output?.exists && output.mediaUrl ? { taskId: null, version: '当前成片', status: 'Succeeded', outputPath: output.assetPath, mediaUrl: output.mediaUrl, exists: true, actual: output.actual, createdAt: null, sourceSnapshot: [] } : null)
})
const selectedEpisodeOutputVersion = computed(() => {
  if (selectedEpisodeOutputTaskId.value !== null) return episodeOutputVersions.value.find(item => String(item.taskId) === String(selectedEpisodeOutputTaskId.value)) || latestEpisodeOutputVersion.value
  return latestEpisodeOutputVersion.value
})
const online = computed(() => health.value?.database?.online && health.value?.comfy?.online)
const gpuText = computed(() => {
  const gpu = health.value?.comfy?.gpu
  if (!gpu) return 'GPU 状态未知'
  return `${gpu.name || 'CUDA'} · ${gpu.freeMiB || 0}/${gpu.totalMiB || 0} MiB 空闲`
})

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  const method = String(options.method || 'GET').toUpperCase()
  if (!(options.body instanceof FormData) && !headers['Content-Type']) headers['Content-Type'] = 'application/json'
  const csrfToken = typeof document === 'undefined' ? auth.csrfToken : (document.cookie.split('; ').find(item => item.startsWith('ai_video_studio_csrf='))?.split('=').slice(1).join('=') || auth.csrfToken)
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken && !headers['X-CSRF-Token']) headers['X-CSRF-Token'] = decodeURIComponent(csrfToken)
  const response = await fetch(path, { ...options, headers, credentials: 'include' })
  const text = await response.text()
  let data = {}
  try { data = text ? JSON.parse(text) : {} } catch { data = { raw: text } }
  if (!response.ok) throw new Error(data.error || data.raw || `请求失败 HTTP ${response.status}`)
  return data
}

async function loadAuthStatus() {
  try {
    const status = await api('/api/auth/status')
    Object.assign(auth, { configured: false, authenticated: false, setupAllowed: false, loginRequired: true, accessMode: 'Password', username: '', role: '', csrfToken: '', expiresAt: null }, status)
    authError.value = ''
  } catch (error) {
    authError.value = error.message
  } finally {
    authReady.value = true
  }
}

async function submitAuth() {
  if (!authForm.username.trim() || !authForm.password) { authError.value = '请填写本机管理员账号和密码'; return }
  if (!auth.configured && authForm.password !== authForm.confirmPassword) { authError.value = '两次输入的密码不一致'; return }
  authBusy.value = true
  authError.value = ''
  try {
    const endpoint = auth.configured ? '/api/auth/login' : '/api/auth/setup'
    const result = await api(endpoint, { method: 'POST', body: JSON.stringify({ username: authForm.username.trim(), password: authForm.password }) })
    Object.assign(auth, { configured: true, authenticated: true, setupAllowed: false, username: result.username, role: result.role, csrfToken: result.csrfToken, expiresAt: result.expiresAt })
    authForm.password = ''
    authForm.confirmPassword = ''
    await loadActive()
  } catch (error) {
    authError.value = error.message
  } finally {
    authBusy.value = false
  }
}

async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }) } catch (error) { ElMessage.error(error.message) }
  Object.assign(auth, { authenticated: false, role: '', csrfToken: '', expiresAt: null })
  errorText.value = ''
  authForm.password = ''
}

async function refreshHealth() {
  try { health.value = await api('/api/health'); errorText.value = '' } catch (error) { errorText.value = error.message }
}

async function loadDashboard() {
  try { Object.assign(dashboard, await api('/api/dashboard')) } catch (error) { errorText.value = error.message }
}

async function loadProjects() {
  projects.value = await api('/api/projects')
  if (selectedProject.value) {
    const found = projects.value.find(x => x.id === selectedProject.value.id)
    if (found) await selectProject(found)
    else if (projects.value[0]) await selectProject(projects.value[0])
  } else if (projects.value[0]) {
    await selectProject(projects.value[0])
  }
}

async function selectProject(project) {
  const selectionVersion = ++projectSelectionVersion
  ++episodeSelectionVersion
  selectedProject.value = project
  selectedEpisode.value = null
  episodeOutput.value = null
  selectedEpisodeOutputTaskId.value = null
  episodeOutputDialog.value = false
  clearEpisodeOutputPolling()
  episodeOutputLoading.value = false
  episodes.value = []
  shots.value = []
  const projectEpisodes = await api(`/api/projects/${project.id}/episodes`)
  if (selectionVersion !== projectSelectionVersion || String(selectedProject.value?.id) !== String(project.id)) return
  episodes.value = projectEpisodes
  if (episodes.value[0]) await selectEpisode(episodes.value[0])
}

async function selectEpisode(episode) {
  if (!selectedProject.value || String(episode.projectId) !== String(selectedProject.value.id)) return
  const selectionVersion = ++episodeSelectionVersion
  selectedEpisode.value = episode
  episodeOutput.value = null
  selectedEpisodeOutputTaskId.value = null
  clearEpisodeOutputPolling()
  const [episodeShots, output] = await Promise.all([
    api(`/api/episodes/${episode.id}/shots`),
    loadEpisodeOutput(episode.id, selectionVersion)
  ])
  if (selectionVersion !== episodeSelectionVersion || String(selectedEpisode.value?.id) !== String(episode.id)) return
  shots.value = episodeShots.map(normalizeShotMedia)
  applyEpisodeOutput(output)
}

async function loadEpisodeOutput(episodeId, selectionVersion = null) {
  if (!episodeId) return null
  episodeOutputLoading.value = true
  try {
    return await api(`/api/episodes/${episodeId}/output`)
  } catch (error) {
    return { exists: false, error: error.message }
  } finally {
    if (selectionVersion === null || selectionVersion === episodeSelectionVersion) episodeOutputLoading.value = false
  }
}

async function refreshEpisodeOutput() {
  const episode = selectedEpisode.value
  if (!episode) return
  const selectionVersion = episodeSelectionVersion
  const output = await loadEpisodeOutput(episode.id, selectionVersion)
  if (selectionVersion !== episodeSelectionVersion || String(selectedEpisode.value?.id) !== String(episode.id)) return
  applyEpisodeOutput(output)
}

async function queueFormalEpisodeRender() {
  if (!selectedEpisode.value) return
  try {
    const result = await api('/api/episode/render', { method: 'POST', body: JSON.stringify({ episodeId: selectedEpisode.value.id, includeSubtitles: true }) })
    await refreshEpisodeOutput()
    ElMessage.success(`整集成片 V${result.version} 已加入合成队列`)
  } catch (error) {
    ElMessage.error(error.message)
  }
}

async function queueEpisodePreview() {
  if (!selectedEpisode.value) return
  try {
    const result = await api('/api/episode/render', { method: 'POST', body: JSON.stringify({ episodeId: selectedEpisode.value.id, includeSubtitles: true, preview: true }) })
    await refreshEpisodeOutput()
    ElMessage.success(`审核预览 V${result.version} 已加入队列；它不会覆盖正式成片`)
  } catch (error) {
    ElMessage.error(error.message)
  }
}

function applyEpisodeOutput(output) {
  episodeOutput.value = output
  if (selectedEpisodeOutputTaskId.value === null && output?.latestVersion?.taskId) selectedEpisodeOutputTaskId.value = output.latestVersion.taskId
  scheduleEpisodeOutputPolling(output)
}

function clearEpisodeOutputPolling() {
  if (episodeOutputPoller !== null && typeof window !== 'undefined') window.clearTimeout(episodeOutputPoller)
  episodeOutputPoller = null
}

function scheduleEpisodeOutputPolling(output) {
  clearEpisodeOutputPolling()
  if (!output?.activeTask || !selectedEpisode.value || typeof window === 'undefined') return
  const episodeId = selectedEpisode.value.id
  episodeOutputPoller = window.setTimeout(async () => {
    if (selectedEpisode.value?.id === episodeId) await refreshEpisodeOutput()
  }, 3500)
}

function openEpisodeOutput(version = null) {
  const outputVersion = version?.mediaUrl ? version : latestEpisodeOutputVersion.value
  selectedEpisodeOutputTaskId.value = outputVersion?.taskId || null
  episodeOutputDialog.value = true
}

function downloadEpisodeOutput(version = selectedEpisodeOutputVersion.value) {
  if (!version?.mediaUrl) return
  const link = document.createElement('a')
  link.href = version.mediaUrl
  link.download = `episode-v${version.version || 'output'}.mp4`
  document.body.appendChild(link)
  link.click()
  link.remove()
}

function episodeRenderStage(task) {
  if (!task) return ''
  if (task.status === 'Pending') return '等待合成队列'
  const progress = Number(task.progress || 0)
  if (progress < 0.15) return '准备镜头素材'
  if (progress < 0.5) return '正在拼接镜头'
  if (progress < 0.75) return '正在输出高清成片'
  if (progress < 0.95) return '正在混入音频与字幕'
  return '正在保存成片结果'
}

function episodeOutputStatusLabel(status) {
  if (status === 'PreviewReady') return '审核预览就绪'
  if (status === 'PreviewStale') return '审核预览已过期'
  return ({ Empty: '尚未合成', Rendering: '正在合成', Ready: '最新成片可用', Stale: '素材已更新', Failed: '最近一次合成失败' })[status] || '状态待确认'
}

function episodeOutputStatusType(status) {
  if (status === 'PreviewReady') return 'info'
  if (status === 'PreviewStale') return 'warning'
  return ({ Empty: 'info', Rendering: 'warning', Ready: 'success', Stale: 'warning', Failed: 'danger' })[status] || 'info'
}

function normalizeShotMedia(shot) {
  const inputImagePath = shot.inputImageAssetPath || null
  const selectedKeyframePath = shot.selectedKeyframeAssetPath || null
  const videoPath = shot.videoAssetPath || null
  const finalVideoPath = shot.finalVideoAssetPath || null
  const resultPath = finalVideoPath || videoPath || selectedKeyframePath || shot.resultAssetPath || null
  return { ...shot, inputImagePath, selectedKeyframePath, videoPath, finalVideoPath, resultPath, resultMediaUrl: shot.resultMediaUrl || shot.finalVideoMediaUrl || shot.videoMediaUrl || shot.selectedKeyframeMediaUrl || null }
}

async function loadCharacters() { characters.value = (await api('/api/characters')).map(row => ({ ...row, referencePath: row.referenceAssetPath || null })) }
async function loadScenes() { scenes.value = (await api('/api/scenes')).map(row => ({ ...row, referencePath: row.referenceAssetPath || null })) }
async function loadTasks() { tasks.value = await api('/api/tasks?limit=150') }
async function loadAssets() { assets.value = (await api('/api/assets')).map(row => ({ ...row, path: row.assetPath || null })) }
async function loadScripts() { scripts.value = await api('/api/scripts') }
async function loadWorkflows() { const [workflowRows, modelRows, presetRows, contractCatalog] = await Promise.all([api('/api/workflows'), api('/api/models'), api('/api/presets'), api('/api/workflow-contracts')]); workflows.value = workflowRows; models.value = modelRows; presets.value = presetRows; workflowContracts.value = contractCatalog }
async function loadSystem() { await refreshHealth(); settings.value = await api('/api/system/settings') }
async function loadReleaseCandidates() {
  if (!qaSelectedEpisode.value) { releaseCandidates.value = []; return }
  releaseCandidatesLoading.value = true
  try { releaseCandidates.value = await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/release-candidates`); releaseCandidatesError.value = '' }
  catch (error) { releaseCandidates.value = []; releaseCandidatesError.value = error.message || '候选包表暂不可用' }
  finally { releaseCandidatesLoading.value = false }
}
async function loadQaDetail() {
  if (!qaSelectedEpisode.value) { qaDetail.value = null; return }
  const detail = await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}`)
  try { detail.releaseEligibility = await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/release-eligibility`) } catch { detail.releaseEligibility = null }
  qaDetail.value = detail
  await loadReleaseCandidates()
}
async function loadQa() {
  qaEpisodes.value = await api('/api/qa/episodes')
  qaSelectedEpisode.value = qaEpisodes.value.find(x => x.id === qaSelectedEpisode.value?.id) || qaEpisodes.value[0] || null
  await loadQaDetail()
}
async function checkShotQa(shot) {
  try { await api(`/api/qa/shots/${shot.id}/check`, { method: 'POST', body: JSON.stringify({ preset: qaPreset.value, autoRetry: true }) }); ElMessage.success('镜头 QA 已加入 CPU 队列'); await loadQaDetail() } catch (error) { ElMessage.error(error.message) }
}
async function checkEpisodeQa() {
  if (!qaSelectedEpisode.value) return
  try { await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/check`, { method: 'POST', body: JSON.stringify({ preset: qaPreset.value, autoRetry: true }) }); ElMessage.success('剧集质量验收已加入 CPU 队列'); await loadQa() } catch (error) { ElMessage.error(error.message) }
}
async function reviewShotQa(shot, decision) {
  const overrideHardFailure = decision === 'Passed' && String(shot.qaStatus || '').toLowerCase() === 'rejected'
  try {
    const note = await ElMessageBox.prompt(overrideHardFailure ? '自动 QA 已拒绝；人工通过必须填写 Override 复核说明' : '可填写审核备注（可留空）', `${statusLabel(decision)} · ${shot.title}`, { inputValue: '', inputValidator: value => overrideHardFailure && !String(value || '').trim() ? 'Override 复核说明不能为空' : true, inputErrorMessage: '请填写人工 Override 复核说明' })
    await api(`/api/qa/shots/${shot.id}/review`, { method: 'POST', body: JSON.stringify({ decision, reviewer: 'local-user', note: note.value, overrideHardFailure }) })
    ElMessage.success('镜头审核已保存'); await loadQa()
  } catch (error) { if (error !== 'cancel') ElMessage.error(error.message) }
}
async function reviewEpisodeQa(decision) {
  if (!qaSelectedEpisode.value) return
  const overrideHardFailure = decision === 'Approved' && String(qaSelectedEpisode.value.qaStatus || '').toLowerCase() === 'rejected'
  try {
    const note = await ElMessageBox.prompt(overrideHardFailure ? '自动 Episode QA 已拒绝；批准必须填写 Override 复核说明' : '可填写剧集审核备注（可留空）', `${statusLabel(decision)} · ${qaSelectedEpisode.value.name}`, { inputValue: '', inputValidator: value => overrideHardFailure && !String(value || '').trim() ? 'Override 复核说明不能为空' : true, inputErrorMessage: '请填写人工 Override 复核说明' })
    await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/review`, { method: 'POST', body: JSON.stringify({ decision, reviewer: 'local-user', note: note.value, overrideHardFailure }) })
    ElMessage.success(`剧集已标记为 ${statusLabel(decision)}`); await loadQa()
  } catch (error) { if (error !== 'cancel') ElMessage.error(error.message) }
}
async function unlockQaEpisode() { try { await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/unlock`, { method: 'POST' }); ElMessage.success('剧集已解锁'); await loadQa() } catch (error) { ElMessage.error(error.message) } }
async function regenerateQaShot(shot) { try { await api(`/api/qa/shots/${shot.id}/regenerate`, { method: 'POST', body: JSON.stringify({ preset: qaPreset.value, autoRetry: true }) }); ElMessage.success('已提交 QA 定向重生成'); await loadQa() } catch (error) { ElMessage.error(error.message) } }
function currentReleaseEligibility() { return qaDetail.value?.releaseEligibility || null }
function modelBindingText(eligibility) {
  const rows = (eligibility?.sourceManifest?.shots || []).flatMap(shot => Object.entries(shot.modelFingerprints || {}).map(([name, hash]) => `${name} sha256=${hash}`))
  return [...new Set(rows)].join('\n')
}
function resetReleaseCandidateForm() {
  const eligibility = currentReleaseEligibility()
  Object.assign(releaseCandidateForm, { licenseEvidenceConfirmed: false, licenseReference: '', licenseScope: '', licenseModels: modelBindingText(eligibility), assetVersionBinding: eligibility?.sourceManifestSha256 || '', licenseTerritory: '', licensePlatforms: '', aiDisclosureRecorded: false, aiDisclosure: '', aiDisclosurePath: '', note: '' })
  releaseCandidateRequestKey.value = `candidate:${qaSelectedEpisode.value?.id || 0}:${Date.now()}:${globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`
}
function openReleaseCandidateDialog() {
  if (!qaSelectedEpisode.value) return
  resetReleaseCandidateForm()
  releaseCandidateDialog.value = true
}
async function createReleaseCandidate() {
  if (!qaSelectedEpisode.value) return
  releaseCandidateCreating.value = true
  try {
    const result = await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/release-candidates`, { method: 'POST', headers: { 'Idempotency-Key': releaseCandidateRequestKey.value }, body: JSON.stringify(releaseCandidateForm) })
    releaseCandidateDialog.value = false
    ElMessage.success(result.candidate?.status === 'Ready' ? '发布候选包已 Ready，可选择版本导出' : '候选包已记录，但当前仍被门禁阻断')
    await loadQaDetail()
  } catch (error) {
    await loadReleaseCandidates()
    ElMessage.error(error.message)
  } finally { releaseCandidateCreating.value = false }
}
async function exportQaEpisode() {
  if (!qaSelectedEpisode.value) return
  await loadReleaseCandidates()
  if (!readyReleaseCandidates.value.length) {
    ElMessage.warning('没有可导出的 Ready 候选包；请先创建候选包并补齐许可证据、AI 披露和审核门禁')
    return
  }
  releaseExportCandidateId.value = readyReleaseCandidates.value[0].id
  releaseExportDialog.value = true
}
async function confirmReleaseExport() {
  if (!qaSelectedEpisode.value || !releaseExportCandidateId.value) return
  releaseExporting.value = true
  try {
    const result = await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/export`, { method: 'POST', body: JSON.stringify({ candidateId: Number(releaseExportCandidateId.value), includeSubtitles: true, includeCover: true }) })
    releaseExportDialog.value = false
    ElMessage.success(`主片导出任务已提交：${result.taskId} · 候选 V${result.candidateVersion}`)
    await loadQaDetail()
  } catch (error) { ElMessage.error(error.message) }
  finally { releaseExporting.value = false }
}

async function loadActive() {
  if (!workbenchAvailable.value) return
  loading.value = true
  try {
    await refreshHealth()
    if (active.value === 'dashboard') await loadDashboard()
    if (active.value === 'projects') { await loadProjects(); await loadScenes(); await loadCharacters(); await loadWorkflows() }
    if (active.value === 'characters') await loadCharacters()
    if (active.value === 'scenes') await loadScenes()
    if (active.value === 'scripts') { await loadProjects(); await loadScripts() }
    if (active.value === 'production') { await loadProjects(); if (selectedProject.value) await selectProject(selectedProject.value); if (selectedEpisode.value) productionStatus.value = await api(`/api/production/status?episodeId=${selectedEpisode.value.id}`) }
    if (active.value === 'qa') await loadQa()
    if (active.value === 'voice') await loadTasks()
    if (active.value === 'sfx') await loadAssets()
    if (active.value === 'tasks') await loadTasks()
    if (active.value === 'assets') await loadAssets()
    if (active.value === 'workflows') await loadWorkflows()
    if (active.value === 'system') await loadSystem()
    errorText.value = ''
  } catch (error) { errorText.value = error.message }
  finally { loading.value = false }
}

watch(active, (value) => {
  if (typeof window !== 'undefined' && window.location.hash !== `#${value}`) window.history.replaceState(null, '', `#${value}`)
  if (workbenchAvailable.value) loadActive()
})
onMounted(async () => {
  await refreshHealth()
  await loadAuthStatus()
  if (workbenchAvailable.value) await loadActive()
})
onBeforeUnmount(clearEpisodeOutputPolling)

function requireText(value, label) {
  if (typeof value !== 'string' || !value.trim()) { ElMessage.warning(`${label}不能为空`); return false }
  return true
}

function resetProject() { Object.assign(projectForm, { id: null, name: '', description: '', status: 'Active', aspectRatio: '16:9', style: '', defaultFps: 30, defaultWidth: 1920, defaultHeight: 1080, promptStyle: '', bgmPath: '', bgmVolume: 0.18 }); projectDialog.value = true }
function editProject(row) { Object.assign(projectForm, { id: row.id, name: row.name, description: row.description || '', status: row.status || 'Active', aspectRatio: row.aspectRatio || '16:9', style: row.style || '', defaultFps: row.defaultFps || 30, defaultWidth: row.defaultWidth || 1920, defaultHeight: row.defaultHeight || 1080, promptStyle: row.promptStyle || '', bgmPath: row.bgmPath || '', bgmVolume: row.bgmVolume || 0.18 }); projectDialog.value = true }
async function saveProject() {
  if (!requireText(projectForm.name, '项目名称')) return
  try {
    if (projectForm.id) await api(`/api/projects/${projectForm.id}`, { method: 'PUT', body: JSON.stringify(projectForm) })
    else await api('/api/projects', { method: 'POST', body: JSON.stringify(projectForm) })
    projectDialog.value = false; await loadProjects(); ElMessage.success('项目已保存')
  } catch (error) { ElMessage.error(error.message) }
}
async function deleteProject(row) {
  try { await ElMessageBox.confirm(`确认删除项目“${row.name}”及其集、镜头任务吗？`, '危险操作', { type: 'warning' }); await api(`/api/projects/${row.id}`, { method: 'DELETE' }); if (selectedProject.value?.id === row.id) selectedProject.value = null; await loadProjects(); ElMessage.success('项目已删除') } catch (error) { if (error !== 'cancel') ElMessage.error(error.message) }
}

function openEpisodeDialog() { Object.assign(episodeForm, { id: null, projectId: selectedProject.value?.id, episodeNumber: episodes.value.length + 1, name: `第 ${episodes.value.length + 1} 集`, description: '', targetSeconds: 60, outputFps: 30, outputWidth: 1920, outputHeight: 1080 }); episodeDialog.value = true }
async function saveEpisode() {
  if (!episodeForm.projectId) return ElMessage.warning('请先选择项目')
  if (!requireText(episodeForm.name, '集名称')) return
  try { await api('/api/episodes', { method: 'POST', body: JSON.stringify(episodeForm) }); episodeDialog.value = false; await selectProject(selectedProject.value); ElMessage.success('集已创建') } catch (error) { ElMessage.error(error.message) }
}
function openShotDialog() {
  if (!selectedProject.value || !selectedEpisode.value) return ElMessage.warning('请先选择项目和集')
  const qualityWorkflow = videoWorkflows.value.find(item => /12_ltx_face_stable_v3/i.test(`${item.name || ''} ${item.path || ''}`))
    || videoWorkflows.value.find(item => /03_ltx_character_lock/i.test(`${item.name || ''} ${item.path || ''}`))
    || videoWorkflows.value.find(item => /wan2[._-]?2|wan/i.test(`${item.name || ''} ${item.modelName || ''}`))
  Object.assign(shotForm, { id: null, projectId: selectedProject.value.id, episodeId: selectedEpisode.value.id, shotNumber: shots.value.length + 1, title: `镜头 ${String(shots.value.length + 1).padStart(2, '0')}`, sceneId: null, characterIds: [], prompt: '', negativePrompt: '低清晰度，畸形手，额外手指，闪烁，脸部变形，文字，水印', workflowId: qualityWorkflow?.id || null, seed: Math.floor(Math.random() * 900000000), width: 512, height: 320, frames: 121, fps: 24, inputImagePath: '', motionPreset: '电影感慢动作', cameraPreset: '中景', status: 'Draft' })
  if (qualityWorkflow) applyWorkflowDefaults(qualityWorkflow.id)
  shotDialog.value = true
}
function applyWorkflowDefaults(workflowId) {
  const workflow = videoWorkflows.value.find(item => String(item.id) === String(workflowId))
  const identity = `${workflow?.name || ''} ${workflow?.modelName || ''}`.toLowerCase()
  if (identity.includes('wan2_2') || identity.includes('wan2.2') || identity.includes('wan')) {
    Object.assign(shotForm, { width: 512, height: 320, frames: 49 })
    applyInputAspectDefaults()
  } else if (identity.includes('ltx') || identity.includes('face_stable')) {
    Object.assign(shotForm, { width: 320, height: 416, frames: 73 })
    applyInputAspectDefaults()
  }
}
function applyInputAspectDefaults(inputPath = shotForm.inputImagePath) {
  const workflow = videoWorkflows.value.find(item => String(item.id) === String(shotForm.workflowId))
  const identity = `${workflow?.name || ''} ${workflow?.modelName || ''}`.toLowerCase()
  if (!inputPath || (!identity.includes('wan') && !identity.includes('ltx') && !identity.includes('face_stable'))) return
  const image = new Image()
  image.onload = () => {
    const aspect = image.naturalWidth / image.naturalHeight
    if (aspect < 0.9) Object.assign(shotForm, { width: 320, height: 416, frames: 73 })
    else if (aspect > 1.15) Object.assign(shotForm, { width: 512, height: 320 })
    else Object.assign(shotForm, { width: 384, height: 384 })
  }
  image.src = mediaUrl(inputPath)
}
async function saveShot() {
  if (!shotForm.episodeId) return ElMessage.warning('请先选择 Episode')
  if (!requireText(shotForm.title, '镜头标题')) return
  if (!requireText(shotForm.prompt, '正向提示词')) return
  try { await api('/api/shots', { method: 'POST', body: JSON.stringify(shotForm) }); shotDialog.value = false; await selectEpisode(selectedEpisode.value); ElMessage.success('镜头已保存') } catch (error) { ElMessage.error(error.message) }
}
async function queueShot(shot) {
  try {
    const workflow = videoWorkflows.value.find(item => String(item.id) === String(shot.workflowId))
    const contract = workflowContractFor(workflow)
    const workflowIdentity = `${workflow?.name || ''} ${workflow?.path || ''} ${contract?.id || ''}`.toLowerCase()
    const hasCharacter = Array.isArray(shot.characterIds) && shot.characterIds.length > 0
    const isVideoTask = Boolean(shot.inputImageAssetPath)
    const media = contract?.media || {}
    const isLtx = isVideoTask && (workflowIdentity.includes('ltx') || workflowIdentity.includes('face_stable'))
    const hasGuideSlot = Array.isArray(contract?.slots) && contract.slots.some(slot => slot.role === 'guideFrame')
    const targetFrames = Number(media.outputFrames?.[0] || (isLtx ? 73 : workflowIdentity.includes('wan') ? 49 : shot.frames || 121))
    const targetFps = Number(media.nativeFps || shot.fps || 24)
    const inputSlots = isVideoTask ? { firstFrame: shot.inputImageAssetPath, ...(hasGuideSlot ? { guideFrame: shot.inputImageAssetPath } : {}) } : undefined
    const data = { projectId: selectedProject.value?.id, episodeId: selectedEpisode.value?.id, shotId: shot.id, taskType: isVideoTask ? 'ImageToVideo' : 'Image', workflowId: isVideoTask ? shot.workflowId : null, inputImagePath: shot.inputImageAssetPath, maxRetries: 2, parameters: { positive: shot.prompt, negative: shot.negativePrompt, seed: shot.seed, width: Number(media.defaultWidth || shot.width || 512), height: Number(media.defaultHeight || shot.height || 320), frames: targetFrames, fps: targetFps, duration: Number((targetFrames / targetFps).toFixed(3)), faceStabilityPriority: isLtx, motionProfile: isLtx ? 'small' : undefined, inputSlots, referenceProfile: hasCharacter ? 'character' : undefined, referenceRequired: hasGuideSlot, workflowVersion: contract?.fileName || workflow?.path?.split(/[\\/]/).pop(), referenceStrength: isLtx ? 0.45 : undefined, guideFrameIndex: hasGuideSlot ? targetFrames - Number(media.guideFrameOffset || 0) : undefined, allowLongVideo: false } }
    await api('/api/tasks', { method: 'POST', body: JSON.stringify(data) }); ElMessage.success(`镜头 ${shot.shotNumber} 已加入队列`); if (active.value === 'tasks') await loadTasks()
  } catch (error) { ElMessage.error(error.message) }
}
async function concatEpisode() { await queueFormalEpisodeRender() }

function resetCharacter() { Object.assign(characterForm, { id: null, projectId: selectedProject.value?.id || null, name: '', ageSetting: '', faceFeatures: '', hair: '', clothes: '', bodyRatio: '', fixedPrompt: '', negativePrompt: '', anchorPath: '', voiceId: '', voiceSpeed: 1, voicePitch: 0 }); characterDialog.value = true }
function editCharacter(row) { Object.assign(characterForm, row); characterDialog.value = true }
async function saveCharacter() { if (!requireText(characterForm.name, '角色名')) return; try { const method = characterForm.id ? 'PUT' : 'POST'; const path = characterForm.id ? `/api/characters/${characterForm.id}` : '/api/characters'; await api(path, { method, body: JSON.stringify(characterForm) }); characterDialog.value = false; await loadCharacters(); ElMessage.success('角色资产已保存') } catch (error) { ElMessage.error(error.message) } }
async function deleteCharacter(row) { try { await ElMessageBox.confirm(`确认删除角色“${row.name}”及其参考图吗？`, '危险操作', { type: 'warning' }); await api(`/api/characters/${row.id}`, { method: 'DELETE' }); await loadCharacters(); ElMessage.success('角色已删除') } catch (error) { if (error !== 'cancel') ElMessage.error(error.message) } }
function openReferenceUpload(target, defaults) {
  referenceTarget.value = target
  Object.assign(referenceUploadMeta, { stage: defaults.stage, role: defaults.role, changeReason: '' })
  referenceUploadDialog.value = true
}
function chooseReference(row) { openReferenceUpload({ type: 'character', id: row.id }, { stage: 'base', role: 'identity' }) }
function onReferenceFile(event) { referenceFile.value = event.target.files?.[0] || null; uploadReference() }
async function uploadReference() {
  if (!referenceFile.value || !referenceTarget.value) return
  const isCharacter = referenceTarget.value.type === 'character'
  const form = new FormData()
  form.append('file', referenceFile.value)
  form.append('kind', isCharacter ? 'identity' : 'master')
  form.append('isAnchor', 'true')
  form.append('stage', referenceUploadMeta.stage)
  form.append('role', referenceUploadMeta.role)
  form.append('changeReason', referenceUploadMeta.changeReason || '')
  try {
    await api(`/api/${isCharacter ? 'characters' : 'scenes'}/${referenceTarget.value.id}/references`, { method: 'POST', headers: {}, body: form })
    ElMessage.success(`参考图已归档 · ${referenceUploadMeta.stage}`)
    referenceFile.value = null
    referenceUploadDialog.value = false
    await (isCharacter ? loadCharacters() : loadScenes())
  } catch (error) { ElMessage.error(error.message) }
}

async function openShotTakes(shot) {
  takeShot.value = shot
  takeDialog.value = true
  takesLoading.value = true
  try {
    const response = await api(`/api/shots/${shot.id}/takes`)
    takeOptions.value = Array.isArray(response) ? response : []
  } catch (error) {
    ElMessage.error(error.message || '读取镜头版本失败')
    takeOptions.value = []
  } finally {
    takesLoading.value = false
  }
}
async function openCharacterReview(row) {
  characterReviewTarget.value = row
  characterReviewDialog.value = true
  characterReferencesLoading.value = true
  try { characterReferences.value = await api(`/api/characters/${row.id}/references`) } catch (error) { characterReferences.value = []; ElMessage.error(error.message) } finally { characterReferencesLoading.value = false }
}
async function reviewCharacterReference(reference, decision) {
  if (!characterReviewTarget.value) return
  try {
    await api(`/api/characters/${characterReviewTarget.value.id}/references/${reference.id}/review`, { method: 'POST', body: JSON.stringify({ decision, reviewer: 'local-user', note: `角色资产库人工审核：${statusLabel(decision)}` }) })
    await openCharacterReview(characterReviewTarget.value)
    ElMessage.success(`参考图已标记为${statusLabel(decision)}`)
  } catch (error) { ElMessage.error(error.message) }
}

function resetScene() { Object.assign(sceneForm, { id: null, projectId: selectedProject.value?.id || null, name: '', description: '', fixedPrompt: '', negativePrompt: '', style: '电影感、写实风格', anchorPath: '' }); sceneDialog.value = true }
function editScene(row) { Object.assign(sceneForm, row); sceneDialog.value = true }
async function saveScene() { if (!requireText(sceneForm.name, '场景名')) return; try { const method = sceneForm.id ? 'PUT' : 'POST'; const path = sceneForm.id ? `/api/scenes/${sceneForm.id}` : '/api/scenes'; await api(path, { method, body: JSON.stringify(sceneForm) }); sceneDialog.value = false; await loadScenes(); ElMessage.success('场景资产已保存') } catch (error) { ElMessage.error(error.message) } }
async function deleteScene(row) { try { await ElMessageBox.confirm(`确认删除场景“${row.name}”及其参考图吗？`, '危险操作', { type: 'warning' }); await api(`/api/scenes/${row.id}`, { method: 'DELETE' }); await loadScenes(); ElMessage.success('场景已删除') } catch (error) { if (error !== 'cancel') ElMessage.error(error.message) } }
function chooseSceneReference(row) { openReferenceUpload({ type: 'scene', id: row.id }, { stage: 'base', role: 'environment' }) }

function resetScript() { Object.assign(scriptForm, { id: null, projectId: selectedProject.value?.id || projects.value[0]?.id || null, episodeId: selectedEpisode.value?.id || null, title: '第 1 集剧本', content: '', language: 'zh-CN', status: 'Draft' }); scriptDialog.value = true }
function editScript(row) { Object.assign(scriptForm, row); scriptDialog.value = true }
async function saveScript() { if (!scriptForm.projectId) return ElMessage.warning('请先选择项目'); if (!requireText(scriptForm.title, '剧本标题') || !requireText(scriptForm.content, '剧本内容')) return; try { const method = scriptForm.id ? 'PUT' : 'POST'; const path = scriptForm.id ? `/api/scripts/${scriptForm.id}` : '/api/scripts'; await api(path, { method, body: JSON.stringify(scriptForm) }); scriptDialog.value = false; await loadScripts(); ElMessage.success('剧本已保存') } catch (error) { ElMessage.error(error.message) } }
async function analyzeScript(row) { try { analysisResult.value = await api(`/api/scripts/${row.id}/analyze`, { method: 'POST', body: JSON.stringify({ scriptId: row.id, episodeId: row.episodeId, useLlm: true, replaceDraftShots: true }) }); await loadScripts(); if (selectedEpisode.value?.id === analysisResult.value.episodeId) await selectEpisode(selectedEpisode.value); ElMessage.success(`已拆分 ${analysisResult.value.shots.length} 个镜头（${analysisResult.value.provider}）`) } catch (error) { ElMessage.error(error.message) } }
async function startProduction() { if (!selectedEpisode.value) return ElMessage.warning('请先选择项目和剧集'); try { productionStatus.value = await api('/api/production/start', { method: 'POST', headers: { 'Idempotency-Key': `production:${selectedEpisode.value.id}:${crypto.randomUUID()}` }, body: JSON.stringify({ episodeId: selectedEpisode.value.id, mode: 'ManualReview', candidateCount: 2 }) }); ElMessage.success('关键帧任务已按 GPU 串行队列提交') } catch (error) { ElMessage.error(error.message) } }
async function productionAction(action) { try { await api(`/api/production/${action}`, { method: 'POST' }); if (selectedEpisode.value) productionStatus.value = await api(`/api/production/status?episodeId=${selectedEpisode.value.id}`); ElMessage.success(action === 'pause' ? '生产队列已暂停' : '生产队列已继续') } catch (error) { ElMessage.error(error.message) } }
async function refreshProduction() { if (!selectedEpisode.value) return; try { productionStatus.value = await api(`/api/production/status?episodeId=${selectedEpisode.value.id}`); shots.value = await api(`/api/episodes/${selectedEpisode.value.id}/shots`); await refreshEpisodeOutput() } catch (error) { ElMessage.error(error.message) } }
async function selectCandidate(shot) { candidateLoading.value = true; try { const candidates = (await api(`/api/shots/${shot.id}/candidates`)).map(row => ({ ...row, path: row.assetPath || null })); if (!candidates.length) return ElMessage.warning('该镜头还没有关键帧候选'); candidateShot.value = shot; candidateOptions.value = candidates; candidateDialog.value = true } catch (error) { ElMessage.error(error.message) } finally { candidateLoading.value = false } }
async function confirmCandidate(candidate) { if (!candidateShot.value) return; try { await api(`/api/shots/${candidateShot.value.id}/candidates/${candidate.id}/select`, { method: 'POST' }); await api(`/api/shots/${candidateShot.value.id}/approve-keyframe`, { method: 'POST', headers: { 'Idempotency-Key': `i2v:${candidateShot.value.id}:${candidate.id}` } }); candidateDialog.value = false; await refreshProduction(); ElMessage.success(`已选择候选 ${candidate.candidateIndex || candidate.id} 并提交 I2V`) } catch (error) { ElMessage.error(error.message) } }
async function approveVideo(shot) { try { await api(`/api/shots/${shot.id}/approve-video`, { method: 'POST' }); await refreshProduction(); ElMessage.success('视频已通过，已提交 1080p / 30 FPS 增强') } catch (error) { ElMessage.error(error.message) } }
async function savePrompt(shot) { try { await api(`/api/shots/${shot.id}/prompt`, { method: 'PUT', body: JSON.stringify({ prompt: shot.prompt, negativePrompt: shot.negativePrompt, locked: shot.promptLocked, source: 'user' }) }); ElMessage.success('提示词已保存并记录版本') } catch (error) { ElMessage.error(error.message) } }
async function uploadLibrary(event, bgm) { const file = event.target.files?.[0]; if (!file) return; const form = new FormData(); form.append('file', file); if (!bgm) form.append('category', 'environment'); try { await api(bgm ? '/api/bgm' : '/api/sound-effects', { method: 'POST', headers: {}, body: form }); ElMessage.success('音频素材已归档') } catch (error) { ElMessage.error(error.message) } finally { event.target.value = '' } }
async function renderEpisode() { await queueFormalEpisodeRender() }

async function taskAction(id, action) { try { await api(`/api/tasks/${id}/${action}`, { method: 'POST' }); await loadTasks(); ElMessage.success(action === 'cancel' ? '任务已取消' : '操作已提交') } catch (error) { ElMessage.error(error.message) } }
async function scanWorkflows() { try { const result = await api('/api/workflows/scan', { method: 'POST' }); await loadWorkflows(); ElMessage.success(`已扫描 ${result.scanned} 个工作流`) } catch (error) { ElMessage.error(error.message) } }
function mediaUrl(assetPath) {
  if (!assetPath) return ''
  if (/^(?:https?:)?\/\/|^\/api\/media(?:\?|$)/i.test(assetPath)) return assetPath
  return `/api/media?assetPath=${encodeURIComponent(assetPath)}`
}
function isVideo(path) { return /\.(mp4|mov|webm|mkv)$/i.test(path || '') }
function statusType(status) { return ({ Succeeded: 'success', PreviewReady: 'info', PreviewStale: 'warning', Running: 'warning', Pending: 'info', Failed: 'danger', Cancelled: 'info', Active: 'success', Approved: 'success', Passed: 'success', NeedReview: 'warning', Rejected: 'danger', Checking: 'warning', AutoChecking: 'warning', NotChecked: 'info' })[status] || 'info' }
const statusLabels = {
  PreviewReady: '审核预览就绪', PreviewStale: '审核预览已过期',
  Succeeded: '已完成', Running: '执行中', Pending: '排队中', Failed: '失败', Cancelled: '已取消',
  Active: '制作中', Paused: '已暂停', Archived: '已归档', Draft: '草稿', Ready: '待生成',
  ImageGenerating: '图片生成中', ImageReview: '关键帧待审核', VideoGenerating: '视频生成中', VideoReview: '视频待审核', PostProcessing: '视频增强中',
  AudioGenerating: '音频生成中', AudioReview: '音频待审核', Queued: '排队中', Retrying: '重试中', Publishing: '发布中', Published: '已发布',
  Completed: '已完成', Approved: '已通过', Passed: '已通过', NeedReview: '待人工复核',
  Rejected: '未通过', Checking: '检查中', AutoChecking: '自动检查中', NotChecked: '未验收'
}
const taskTypeLabels = {
  Image: '图片生成', ImageToVideo: '图生视频', Enhance: '视频增强', EpisodeRender: '剧集合成',
  QAExport: '验收导出', EpisodeQA: 'Episode 验收', ShotQA: '镜头验收', TTS: '语音生成',
  Audio: '音频处理', Subtitle: '字幕生成', Concat: '视频合并', VideoRestore: '视频细节修复'
}
const presetLabels = { Draft: '快速预检', Standard: '标准验收', HighQuality: '高质量发布' }
const issueTypeLabels = {
  Technical: '技术问题', Content: '内容问题', Consistency: '一致性问题', Motion: '动作问题',
  Composition: '构图问题', Semantic: '语义问题', BlackFrame: '黑帧', Decode: '解码问题',
  MissingInput: '缺少输入', MissingOutput: '缺少输出'
}
const severityLabels = { Critical: '严重', Error: '错误', Warning: '警告', Info: '提示' }
const assetTypeLabels = { image: '图片', video: '视频', audio: '音频', workflow: '工作流', model: '模型', subtitle: '字幕' }
const workflowTypeLabels = { image: '图片生成', i2v: '图生视频', imagetovideo: '图生视频', video: '视频处理', enhance: '视频增强' }
const modelTypeLabels = { checkpoint: '主模型', lora: 'LoRA', ipadapter: 'IP-Adapter', vae: 'VAE', text_encoder: '文本编码器', controlnet: 'ControlNet', diffusion: '扩散模型', video: '视频模型' }
const providerLabels = { LocalRules: '本地规则解析', OpenAICompatible: '兼容 API', OpenAI: 'OpenAI' }
function statusLabel(status) { return statusLabels[status] || status || '未设置' }
function taskTypeLabel(taskType) { return taskTypeLabels[taskType] || taskType || '未知任务' }
function presetLabel(preset) { return presetLabels[preset] || preset || '标准验收' }
function issueTypeLabel(issueType) { return issueTypeLabels[issueType] || issueType || '其他问题' }
function severityLabel(severity) { return severityLabels[severity] || severity || '提示' }
function assetTypeLabel(assetType) { return assetTypeLabels[String(assetType || '').toLowerCase()] || assetType || '其他素材' }
function workflowTypeLabel(workflowType) { return workflowTypeLabels[String(workflowType || '').toLowerCase()] || workflowType || '其他工作流' }
function modelTypeLabel(modelType) { return modelTypeLabels[String(modelType || '').toLowerCase()] || modelType || '其他模型' }
function workflowContractFor(workflow) {
  const fileName = String(workflow?.path || workflow?.name || '').split(/[\\/]/).pop()
  return workflowContracts.value?.inventory?.find(item => String(item.fileName || '').toLowerCase() === fileName.toLowerCase()) || workflowContracts.value?.contracts?.find(item => String(item.fileName || '').toLowerCase() === fileName.toLowerCase()) || null
}
function workflowContractLabel(contract) {
  if (!contract) return '未登记'
  if (contract.status && contract.status !== 'Passed') return `未通过：${contract.status}`
  return contract.productionEligible ? '准入 · 正式' : '实验 · 禁止生产'
}
function workflowContractType(contract) {
  if (!contract || contract.status === 'Uncontracted' || contract.status === 'Failed') return 'danger'
  return contract.productionEligible ? 'success' : 'warning'
}
function releaseStatusLabel(status) { return ({ Ready: '可创建候选包', Blocked: '已阻断', Passed: '通过', Failed: '失败', NeedReview: '待人工复核' })[status] || status || '待确认' }
function providerLabel(provider) { return providerLabels[provider] || provider || '本地解析' }
function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-' }
function formatBytes(value) { if (!value) return '-'; const units = ['B', 'KB', 'MB', 'GB']; let n = Number(value); let i = 0; while (n > 1024 && i < units.length - 1) { n /= 1024; i++ } return `${n.toFixed(i ? 1 : 0)} ${units[i]}` }
function formatDuration(value) { const seconds = Number(value); if (!Number.isFinite(seconds)) return '-'; const minutes = Math.floor(seconds / 60); return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, '0')}` }
assetTypeLabels.episode = '剧集成片'
</script>

<template>
  <div v-if="!authReady" class="auth-shell">
    <section class="auth-card"><h1>正在打开工作台</h1><p>正在连接本机服务…</p></section>
  </div>
  <div v-else-if="!workbenchAvailable" class="auth-shell">
    <section class="auth-card">
      <div class="auth-brand"><div class="brand-mark">AI</div><div><div class="brand-title">视频工作室</div><div class="brand-subtitle">本机管理员保护</div></div></div>
      <div class="eyebrow">LOCAL ADMINISTRATION</div>
      <h1>{{ authReady && !auth.configured ? '创建本机管理员账号' : '登录本机后台' }}</h1>
      <p v-if="authReady && !auth.configured">首次使用需要创建一个本机管理员账号。密码只保存为不可逆校验值，不会写入前端或日志。</p>
      <p v-else>此后台仅监听本机地址。登录后才能查看或修改项目、角色、任务和素材。</p>
      <el-form label-position="top" @submit.prevent="submitAuth">
        <el-form-item label="本机管理员账号"><el-input v-model="authForm.username" autocomplete="username" placeholder="例如：studio-admin" :disabled="!authReady || authBusy" /></el-form-item>
        <el-form-item label="本机管理员密码"><el-input v-model="authForm.password" type="password" show-password autocomplete="current-password" placeholder="至少 12 位" :disabled="!authReady || authBusy" @keyup.enter="submitAuth" /></el-form-item>
        <el-form-item v-if="authReady && !auth.configured" label="确认密码"><el-input v-model="authForm.confirmPassword" type="password" show-password autocomplete="new-password" placeholder="再次输入本机管理员密码" :disabled="authBusy" @keyup.enter="submitAuth" /></el-form-item>
        <div v-if="authError" class="auth-error">{{ authError }}</div>
        <div v-if="authReady && !auth.configured && !auth.setupAllowed" class="auth-error">当前请求不是受支持的本机页面来源，不能初始化管理员账号。</div>
        <el-button type="primary" native-type="submit" class="auth-submit" :loading="authBusy" :disabled="!authReady || (!auth.configured && !auth.setupAllowed)">{{ !authReady ? '正在检查本机服务' : (auth.configured ? '登录后台' : '创建并登录') }}</el-button>
      </el-form>
      <div class="auth-status"><span class="connection-dot" :class="{ online: health?.database?.online }"></span><span>数据库 {{ health?.database?.online ? '在线' : '待连接' }} · 服务仅允许 127.0.0.1 / localhost</span></div>
    </section>
  </div>

  <div v-else class="studio-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">AI</div><div><div class="brand-title">视频工作室</div><div class="brand-subtitle">本地 AI 视频生产系统</div></div></div>
      <div class="side-section">制作中枢</div>
      <button v-for="item in navItems" :key="item.id" class="nav-item" :class="{ active: active === item.id }" @click="active = item.id"><span class="nav-icon">{{ item.icon }}</span><span><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span></button>
      <div class="sidebar-footer"><div class="connection-dot" :class="{ online }"></div><div><strong>{{ online ? '本地链路正常' : '等待服务连接' }}</strong><small>127.0.0.1 · RTX 4070</small></div></div>
    </aside>

    <main class="main-stage">
      <header class="topbar" :class="{ 'character-library-header': active === 'character-library' }"><div><div class="eyebrow">AI 视频 / 工作区</div><h1>{{ currentNav.label }}</h1><p>{{ currentNav.hint }}</p></div><div class="top-actions"><el-tag :type="health?.comfy?.online ? 'success' : 'danger'" effect="dark">ComfyUI {{ health?.comfy?.online ? '在线' : '离线' }}</el-tag><el-tag type="info" effect="dark">{{ gpuText }}</el-tag><el-tag type="success" effect="plain">{{ auth.loginRequired ? auth.username : '本机免登录' }}</el-tag><el-button v-if="auth.loginRequired" plain @click="logout">退出登录</el-button><el-button circle plain @click="loadActive" :loading="loading">↻</el-button></div></header>
      <div v-if="errorText" class="error-banner"><span>连接提示：{{ errorText }}</span><el-button link @click="errorText = ''">关闭</el-button></div>

      <section v-if="active === 'dashboard'" class="page-content">
        <div class="hero-panel"><div><div class="eyebrow">生产控制</div><h2>把灵感变成可连续生产的镜头。</h2><p>角色、场景、工作流、任务和输出都落到本地资产库，适配 RTX 4070 12GB 的串行 GPU 队列。</p><div class="hero-buttons"><el-button type="primary" @click="active = 'projects'">进入项目制作</el-button><el-button plain @click="active = 'tasks'">查看任务队列</el-button></div></div><div class="hero-orbit"><div class="orbit-ring ring-1"></div><div class="orbit-ring ring-2"></div><div class="orbit-core">{{ dashboard.counts.succeededTasks || 0 }}<small>完成任务</small></div></div></div>
        <div class="stat-grid"><div class="stat-card" v-for="stat in [{label:'项目',key:'projects',icon:'▣'},{label:'角色资产',key:'characters',icon:'◎'},{label:'场景资产',key:'scenes',icon:'◇'},{label:'素材',key:'assets',icon:'▤'}]" :key="stat.key"><span class="stat-icon">{{ stat.icon }}</span><div><small>{{ stat.label }}</small><strong>{{ dashboard.counts[stat.key] || 0 }}</strong></div></div></div>
        <div class="dashboard-grid"><div class="panel"><div class="panel-head"><div><div class="eyebrow">GPU 监控</div><h3>显存与服务</h3></div><el-tag :type="health?.database?.online ? 'success' : 'danger'">数据库 {{ health?.database?.online ? '在线' : '待配置' }}</el-tag></div><div class="telemetry"><div class="telemetry-number">{{ health?.comfy?.gpu?.freeMiB || 0 }}<small>MiB 空闲</small></div><div class="telemetry-line"><span>GPU</span><strong>{{ health?.comfy?.gpu?.name || '未检测到' }}</strong></div><div class="telemetry-line"><span>FFmpeg</span><strong>{{ health?.ffmpeg?.available ? '可用' : '未找到' }}</strong></div><div class="telemetry-line"><span>队列策略</span><strong>并发 1 · 自动重试</strong></div></div></div><div class="panel"><div class="panel-head"><div><div class="eyebrow">最近活动</div><h3>最近任务</h3></div><el-button link @click="active = 'tasks'">全部任务 →</el-button></div><el-table :data="dashboard.recentTasks" size="small" class="dark-table"><el-table-column label="类型" width="130"><template #default="scope">{{ taskTypeLabel(scope.row.taskType) }}</template></el-table-column><el-table-column prop="shotTitle" label="镜头" min-width="150"/><el-table-column label="状态" width="110"><template #default="scope"><el-tag size="small" :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column></el-table></div></div>
      </section>

      <MiniMaxLocalPanel v-else-if="active === 'minimax'" :api="api" @navigate="active = $event" />
      <CharacterLibraryPanel v-else-if="active === 'character-library'" :api="api" @navigate="active = $event" />
      <CharacterStoryPanel v-else-if="active === 'character-story'" :api="api" @navigate="active = $event" />
      <section v-else-if="active === 'projects'" class="page-content">
        <div v-if="selectedEpisode" class="episode-preview panel">
          <div class="episode-preview-head">
            <div><div class="eyebrow">正式 Episode 输出</div><h3>{{ selectedEpisode.name }} · 整集成片</h3><span class="muted">这里保存可播放的正式成片、合成状态和历史版本，不与分镜草稿混淆。</span></div>
            <div class="episode-preview-actions">
              <el-button size="small" type="primary" @click="openEpisodeOutput" :loading="episodeOutputLoading">查看整集结果</el-button>
              <el-button size="small" type="success" plain @click="queueFormalEpisodeRender" :disabled="!episodeOutput?.canRender || Boolean(episodeOutput?.activeTask)">{{ latestEpisodeOutputVersion ? '重新合成' : '生成整集成片' }}</el-button>
              <el-button size="small" plain @click="refreshEpisodeOutput" :loading="episodeOutputLoading">刷新状态</el-button>
            </div>
          </div>
          <div v-if="episodeOutputLoading && !episodeOutput" class="episode-empty"><strong>正在读取整集成片状态</strong><span>正在核对正式输出文件和历史合成任务。</span></div>
          <template v-else>
            <div v-if="latestEpisodeOutputVersion" class="episode-result-summary">
              <button class="episode-result-open" @click="openEpisodeOutput"><span class="episode-result-play">▶</span><span><strong>查看整集成片 {{ latestEpisodeOutputVersion.version ? `V${latestEpisodeOutputVersion.version}` : '' }}</strong><small>{{ formatDuration(latestEpisodeOutputVersion.actual?.durationSeconds) }} · {{ latestEpisodeOutputVersion.actual?.width || '-' }}×{{ latestEpisodeOutputVersion.actual?.height || '-' }} · {{ latestEpisodeOutputVersion.actual?.fps ? Number(latestEpisodeOutputVersion.actual.fps).toFixed(0) : '-' }} FPS</small></span></button>
              <div class="episode-summary-meta"><el-tag size="small" :type="episodeOutputStatusType(episodeOutput?.outputStatus)">{{ episodeOutputStatusLabel(episodeOutput?.outputStatus) }}</el-tag><span :class="latestEpisodeOutputVersion.actual?.hasAudio ? 'audio-ok' : 'audio-missing'">音频 {{ latestEpisodeOutputVersion.actual?.hasAudio ? '已包含' : '缺失' }}</span><span v-if="latestEpisodeOutputVersion.actual?.sizeBytes">{{ formatBytes(latestEpisodeOutputVersion.actual.sizeBytes) }}</span><span>{{ formatDate(latestEpisodeOutputVersion.createdAt) }}</span></div>
            </div>
            <div v-if="episodeOutput?.activeTask" class="episode-render-progress"><div><strong>V{{ episodeOutput.activeTask.version }} {{ episodeRenderStage(episodeOutput.activeTask) }}</strong><span>{{ Math.round(Number(episodeOutput.activeTask.progress || 0) * 100) }}% · 会自动刷新</span></div><el-progress :percentage="Math.round(Number(episodeOutput.activeTask.progress || 0) * 100)" :stroke-width="8" status="success"/></div>
            <el-alert v-if="episodeOutput?.latestFailure" :title="`最近一次合成 V${episodeOutput.latestFailure.version} 失败：${episodeOutput.latestFailure.errorMessage || '请重新合成'}`" type="error" :closable="false" show-icon/>
            <div v-if="episodeOutput?.source" class="episode-source-status"><span>镜头素材 {{ episodeOutput.source.ready }} / {{ episodeOutput.source.total }} 已就绪</span><span v-if="episodeOutput.isStale" class="source-stale">分镜素材已更新，当前成片基于旧版本</span><span v-else-if="episodeOutput.renderBlockedReason">{{ episodeOutput.renderBlockedReason }}</span></div>
            <div v-if="!latestEpisodeOutputVersion && !episodeOutput?.activeTask" class="episode-empty"><strong>{{ episodeOutput?.outputStatus === 'Failed' ? '最近一次正式合成失败' : '暂无正式成片' }}</strong><span>{{ episodeOutput?.renderBlockedReason || '完成所有镜头正式视频后，即可生成整集成片。' }}</span></div>
          </template>
        </div>
        <div class="toolbar"><div><div class="eyebrow">项目 / 分集 / 镜头</div><h2>项目制作台</h2></div><div><el-button @click="active='character-story'">人物选角与剧情关键帧</el-button><el-button type="primary" @click="resetProject">＋ 新建项目</el-button></div></div>
        <div class="workspace-grid"><div class="panel project-list"><div class="panel-head"><h3>项目库</h3><span class="muted">{{ projects.length }} 个项目</span></div><div v-for="project in projects" :key="project.id" class="project-row" :class="{ selected: selectedProject?.id === project.id }" @click="selectProject(project)"><div class="project-color"></div><div class="project-main"><strong>{{ project.name }}</strong><small>{{ project.description || '未填写项目简介' }}</small><div class="row-meta"><span>{{ project.episodeCount || 0 }} 集</span><span>{{ project.shotCount || 0 }} 镜头</span><span>{{ project.assetCount || 0 }} 素材</span></div></div><div class="row-actions"><el-button circle text @click.stop="editProject(project)">✎</el-button><el-button circle text type="danger" @click.stop="deleteProject(project)">×</el-button></div></div><el-empty v-if="!projects.length" description="还没有项目，先创建一个制作项目" /></div><div class="panel project-detail"><template v-if="selectedProject"><div class="panel-head"><div><div class="eyebrow">当前项目</div><h3>{{ selectedProject.name }}</h3></div><el-button type="primary" plain @click="openEpisodeDialog">＋ 新建一集</el-button></div><div class="episode-tabs"><button v-for="episode in episodes" :key="episode.id" :class="{ active: selectedEpisode?.id === episode.id }" @click="selectEpisode(episode)">EP {{ String(episode.episodeNumber).padStart(2, '0') }}<small>{{ episode.name }}</small></button><span v-if="!episodes.length" class="muted">尚未创建集</span></div><div v-if="selectedEpisode" class="shot-board"><div class="shot-board-head"><div><strong>{{ selectedEpisode.name }}</strong><span class="muted"> · 目标 {{ selectedEpisode.targetSeconds }} 秒 · {{ selectedEpisode.outputWidth }}×{{ selectedEpisode.outputHeight }}</span></div><div><el-button size="small" @click="openShotDialog">＋ 添加镜头</el-button><el-button size="small" type="success" plain @click="concatEpisode" :disabled="!episodeOutput?.canRender || Boolean(episodeOutput?.activeTask)">生成整集成片</el-button></div></div><div class="shot-grid"><article v-for="shot in shots" :key="shot.id" class="shot-card"><div class="shot-preview" :class="{ empty: !shot.resultPath }"><template v-if="shot.resultPath && isVideo(shot.resultPath)"><video :src="mediaUrl(shot.resultPath)" muted preload="metadata"></video></template><template v-else-if="shot.resultPath"><img :src="mediaUrl(shot.resultPath)" /></template><template v-else><span>{{ String(shot.shotNumber).padStart(2, '0') }}</span><small>等待生成</small></template><label>镜头 {{ String(shot.shotNumber).padStart(2, '0') }}</label></div><div class="shot-body"><strong>{{ shot.title }}</strong><p>{{ shot.cameraPreset || '镜头未设定' }} · {{ shot.motionPreset || '动作未设定' }}</p><el-tag size="small" :type="statusType(shot.status)">{{ statusLabel(shot.status) }}</el-tag><div class="shot-card-actions"><el-button class="shot-run" size="small" type="primary" @click="queueShot(shot)">{{ shot.inputImagePath ? '图生视频' : '生成图片' }}</el-button><el-button size="small" plain @click="openShotTakes(shot)">版本</el-button></div></div></article><div v-if="!shots.length" class="empty-board"><span>＋</span><p>添加第一个镜头，开始搭建连续叙事</p><el-button plain @click="openShotDialog">创建镜头</el-button></div></div></div><el-empty v-else description="先创建一集，再开始添加镜头" /></template><el-empty v-else description="选择左侧项目查看制作内容" /></div></div>
      </section>

      <section v-else-if="active === 'characters'" class="page-content"><div class="toolbar"><div><div class="eyebrow">角色资产库</div><h2>角色资产库</h2></div><el-button type="primary" @click="resetCharacter">＋ 新建角色</el-button></div><div class="asset-grid"><article v-for="character in characters" :key="character.id" class="library-card"><div class="library-cover portrait"><img v-if="character.referencePath" :src="mediaUrl(character.referencePath)" /><span v-else>◎</span><label>{{ character.referenceCount || 0 }} 参考图</label></div><div class="library-content"><div class="card-title"><h3>{{ character.name }}</h3><el-tag size="small" type="success">身份锚点</el-tag></div><p>{{ character.faceFeatures || '尚未填写脸部特征' }}</p><div class="asset-lines"><span>发型</span><strong>{{ character.hair || '-' }}</strong><span>服装</span><strong>{{ character.clothes || '-' }}</strong></div><div class="card-actions"><el-button size="small" @click="editCharacter(character)">编辑</el-button><el-button size="small" plain @click="chooseReference(character)">上传阶段参考</el-button><el-button size="small" plain @click="openCharacterReview(character)">审核参考图</el-button><el-button size="small" type="danger" text @click="deleteCharacter(character)">删除</el-button></div></div></article><div v-if="!characters.length" class="empty-board"><span>◎</span><p>角色资产会在这里保存身份锚点、固定提示词和 LoRA 路径</p><el-button plain @click="resetCharacter">创建角色</el-button></div></div></section>

      <section v-else-if="active === 'scenes'" class="page-content"><div class="toolbar"><div><div class="eyebrow">场景资产库</div><h2>场景资产库</h2></div><el-button type="primary" @click="resetScene">＋ 新建场景</el-button></div><div class="asset-grid"><article v-for="scene in scenes" :key="scene.id" class="library-card"><div class="library-cover landscape"><img v-if="scene.referencePath" :src="mediaUrl(scene.referencePath)" /><span v-else>◇</span><label>{{ scene.referenceCount || 0 }} 参考图</label></div><div class="library-content"><div class="card-title"><h3>{{ scene.name }}</h3><el-tag size="small" type="info">场景主图</el-tag></div><p>{{ scene.description || scene.fixedPrompt || '尚未填写场景描述' }}</p><div class="asset-lines"><span>风格</span><strong>{{ scene.style || '-' }}</strong><span>锚点</span><strong>{{ scene.anchorPath ? '已设置' : '待上传' }}</strong></div><div class="card-actions"><el-button size="small" @click="editScene(scene)">编辑</el-button><el-button size="small" plain @click="chooseSceneReference(scene)">上传主图</el-button><el-button size="small" type="danger" text @click="deleteScene(scene)">删除</el-button></div></div></article><div v-if="!scenes.length" class="empty-board"><span>◇</span><p>把建筑、房间、车辆和自然环境保存成可复用场景</p><el-button plain @click="resetScene">创建场景</el-button></div></div></section>

      <section v-else-if="active === 'scripts'" class="page-content"><div class="toolbar"><div><div class="eyebrow">剧本 / 解析 / 镜头</div><h2>剧本拆分台</h2></div><el-button type="primary" @click="resetScript">＋ 新建剧本</el-button></div><div class="two-col"><div class="panel"><div class="panel-head"><div><h3>剧本版本库</h3><span class="muted">支持 TXT / Markdown 内容粘贴与版本历史</span></div></div><div v-for="script in scripts" :key="script.id" class="script-row" :class="{ selected: selectedScript?.id === script.id }" @click="selectedScript = script"><div><strong>{{ script.title }}</strong><small>{{ script.episodeName || '未绑定集' }} · v{{ script.version }} · {{ statusLabel(script.status) }}</small></div><div class="row-actions"><el-button size="small" text @click.stop="editScript(script)">编辑</el-button><el-button size="small" type="primary" plain @click.stop="analyzeScript(script)">AI 拆分</el-button></div></div><el-empty v-if="!scripts.length" description="先创建一个剧本"/></div><div class="panel"><div class="panel-head"><div><h3>拆分结果</h3><span class="muted">自动识别人物、场景、动作、对白与镜头运动</span></div></div><template v-if="analysisResult"><div class="analysis-banner"><strong>{{ providerLabel(analysisResult.provider) }} 已完成解析</strong><span>{{ analysisResult.shots.length }} 个镜头 · 人物缺失 {{ analysisResult.missingCharacters.length }} · 场景缺失 {{ analysisResult.missingScenes.length }}</span></div><el-alert v-if="analysisResult.missingCharacters.length || analysisResult.missingScenes.length" title="发现待确认资产草稿，不会自动写入正式资产库" type="warning" :closable="false"/><el-table :data="analysisResult.shots" size="small" class="dark-table"><el-table-column prop="shotNumber" label="#" width="60"/><el-table-column prop="title" label="镜头" min-width="150"/><el-table-column prop="action" label="动作" min-width="180"/><el-table-column prop="cameraType" label="景别" width="110"/><el-table-column prop="cameraMotion" label="运动" width="120"/><el-table-column prop="durationSeconds" label="秒" width="65"/></el-table></template><el-empty v-else description="点击剧本右侧的 AI 拆分，生成可审核分镜"/></div></div></section>

      <section v-else-if="active === 'production'" class="page-content"><div class="toolbar"><div><div class="eyebrow">生产中心 / 人工复核</div><h2>剧集生产中心</h2></div><div><el-button plain @click="refreshProduction">刷新状态</el-button><el-button type="primary" @click="startProduction">开始关键帧生产</el-button><el-button type="warning" plain @click="productionAction('pause')">暂停队列</el-button><el-button type="success" plain @click="productionAction('resume')">继续队列</el-button></div></div><div class="panel" v-if="selectedEpisode"><div class="queue-banner"><div><strong>{{ selectedEpisode.name }}</strong><span>默认人工复核 · 关键帧候选数 2 · RTX 4070 GPU 并发 1</span></div><el-button size="small" type="success" plain @click="renderEpisode" :disabled="!episodeOutput?.canRender || Boolean(episodeOutput?.activeTask)">生成整集成片</el-button></div><div class="production-progress"><el-progress :percentage="productionStatus?.run ? Math.round((productionStatus.run.completedShots || 0) / Math.max(1, productionStatus.run.totalShots || shots.length) * 100) : 0" status="success"/><span>{{ productionStatus?.run?.completedShots || 0 }} / {{ productionStatus?.run?.totalShots || shots.length }} 完成</span></div><el-table :data="shots" class="dark-table" stripe><el-table-column prop="shotNumber" label="#" width="60"/><el-table-column prop="title" label="镜头" min-width="180"/><el-table-column prop="cameraType" label="景别" width="110"/><el-table-column prop="durationSeconds" label="时长" width="80"/><el-table-column label="状态" width="130"><template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column><el-table-column label="质量" width="80"><template #default="scope">{{ scope.row.qualityScore ? Number(scope.row.qualityScore).toFixed(0) : '-' }}</template></el-table-column><el-table-column label="提示词" min-width="280"><template #default="scope"><el-input v-model="scope.row.prompt" size="small" @change="savePrompt(scope.row)"/><small class="table-sub">v{{ scope.row.promptVersion || 1 }} · {{ scope.row.promptLocked ? '已锁定' : '可覆盖' }}</small></template></el-table-column><el-table-column label="审核" width="190" fixed="right"><template #default="scope"><el-button v-if="scope.row.status === 'VideoReview'" size="small" type="success" plain @click="approveVideo(scope.row)">通过视频并增强</el-button><el-button v-else size="small" plain @click="selectCandidate(scope.row)" :disabled="!['ImageReview','Ready'].includes(scope.row.status)">选关键帧并生成视频</el-button></template></el-table-column></el-table></div><el-empty v-else description="请先在项目制作台选择项目和 Episode"/></section>

      <section v-else-if="active === 'qa'" class="page-content">
        <div class="toolbar"><div><div class="eyebrow">视频质量验收 / 发布门禁</div><h2>质量验收中心</h2></div><div class="qa-toolbar"><el-select v-model="qaPreset" size="small" style="width:150px"><el-option label="快速预检" value="Draft"/><el-option label="标准验收" value="Standard"/><el-option label="高质量发布" value="HighQuality"/></el-select><el-button plain @click="loadQa">刷新验收</el-button></div></div>
        <div class="qa-note panel"><div><strong>三层验收</strong><span>技术硬标准 → 镜头内容/稳定性 → 剧集连续性与发布锁定</span></div><small>没有大型视觉模型时，人物身份、动作语义、构图和跨镜头连续性会明确进入人工复核，不自动放行。</small></div>
        <div class="qa-layout"><div class="panel qa-episode-list"><div class="panel-head"><h3>剧集列表</h3><span class="muted">{{ qaEpisodes.length }} 集</span></div><button v-for="episode in qaEpisodes" :key="episode.id" class="qa-episode-row" :class="{ selected: qaSelectedEpisode?.id === episode.id }" @click="qaSelectedEpisode = episode; loadQaDetail()"><div><strong>{{ episode.name }}</strong><small>EP {{ String(episode.episodeNumber).padStart(3, '0') }} · {{ episode.shotCount || 0 }} 镜头</small></div><div class="qa-episode-score"><el-tag size="small" :type="statusType(episode.qaStatus)">{{ statusLabel(episode.qaStatus) }}</el-tag><strong>{{ episode.overallScore ? Number(episode.overallScore).toFixed(0) : '-' }}</strong></div></button><el-empty v-if="!qaEpisodes.length" description="还没有可验收的剧集"/></div>
          <div class="panel qa-detail"><template v-if="qaDetail"><div class="panel-head"><div><div class="eyebrow">剧集验收详情</div><h3>{{ qaDetail.episode.name }}</h3><span class="muted">技术标准：{{ presetLabel(qaPreset) }} · 目标 {{ qaDetail.episode.outputWidth }}×{{ qaDetail.episode.outputHeight }} / {{ qaDetail.episode.outputFps }} FPS</span></div><div class="qa-head-actions"><el-tag :type="statusType(qaDetail.episode.qaStatus)">{{ statusLabel(qaDetail.episode.qaStatus) }}</el-tag><el-tag v-if="qaDetail.episode.qaLocked" type="success">已锁定</el-tag><strong class="qa-big-score">{{ qaDetail.episode.overallScore ? Number(qaDetail.episode.overallScore).toFixed(0) : '-' }}</strong></div></div><div class="qa-actions"><el-button type="primary" @click="checkEpisodeQa">自动验收 Episode</el-button><el-button type="success" plain @click="reviewEpisodeQa('Approved')" :disabled="qaDetail.episode.qaLocked">通过并锁定</el-button><el-button plain @click="reviewEpisodeQa('NeedReview')">标记为人工复核</el-button><el-button plain @click="unlockQaEpisode" :disabled="!qaDetail.episode.qaLocked">解锁</el-button><el-button type="warning" plain @click="exportQaEpisode" :disabled="!qaDetail.episode.qaLocked">导出主片</el-button></div><div v-if="qaDetail.releaseEligibility" class="release-gate-strip"><strong>发布候选门禁：{{ releaseStatusLabel(qaDetail.releaseEligibility.releaseEligibility) }}</strong><span>技术 {{ releaseStatusLabel(qaDetail.releaseEligibility.technicalStatus) }} · 内容 {{ releaseStatusLabel(qaDetail.releaseEligibility.contentStatus) }}</span><small v-if="qaDetail.releaseEligibility.blockingReasons?.length">{{ qaDetail.releaseEligibility.blockingReasons.slice(0, 3).join("；") }}</small></div><el-table :data="qaDetail.shots" class="dark-table qa-table" stripe><el-table-column label="#" width="55"><template #default="scope">{{ scope.row.shot.shotNumber }}</template></el-table-column><el-table-column label="镜头" min-width="180"><template #default="scope"><strong>{{ scope.row.shot.title }}</strong><small class="table-sub">{{ scope.row.shot.sceneName || '未绑定场景' }}</small></template></el-table-column><el-table-column label="QA 状态" width="120"><template #default="scope"><el-tag size="small" :type="statusType(scope.row.shot.qaStatus)">{{ statusLabel(scope.row.shot.qaStatus) }}</el-tag></template></el-table-column><el-table-column label="得分" width="75"><template #default="scope">{{ scope.row.shot.qaScore ? Number(scope.row.shot.qaScore).toFixed(0) : '-' }}</template></el-table-column><el-table-column label="问题" width="75"><template #default="scope">{{ scope.row.issues?.length || 0 }}</template></el-table-column><el-table-column label="审核操作" min-width="330" fixed="right"><template #default="scope"><el-button size="small" type="primary" plain @click="checkShotQa(scope.row.shot)">验收</el-button><el-button size="small" type="success" plain @click="reviewShotQa(scope.row.shot, 'Passed')">通过</el-button><el-button size="small" type="danger" plain @click="reviewShotQa(scope.row.shot, 'Rejected')">拒绝</el-button><el-button size="small" type="warning" plain @click="regenerateQaShot(scope.row.shot)">重生成</el-button></template></el-table-column></el-table><div class="qa-issue-board"><div class="panel-head"><h3>剧集级问题</h3><span class="muted">{{ qaDetail.episodeIssues?.length || 0 }} 条</span></div><div v-for="issue in qaDetail.episodeIssues" :key="issue.id" class="qa-issue"><el-tag size="small" :type="issue.severity === 'Critical' || issue.severity === 'Error' ? 'danger' : 'warning'">{{ severityLabel(issue.severity) }}</el-tag><span>{{ issue.description }}</span><small>{{ issueTypeLabel(issue.issueType) }}</small></div><el-empty v-if="!qaDetail.episodeIssues?.length" description="暂无 剧集级问题" :image-size="50"/></div></template><el-empty v-else description="从左侧选择剧集查看验收详情"/></div></div>
      </section>

      <VoiceStudioPanel v-else-if="active === 'voice'" :api="api" @task-created="loadTasks" />

      <section v-else-if="active === 'sfx'" class="page-content"><div class="toolbar"><div><div class="eyebrow">音效库</div><h2>音效与 BGM</h2></div><span class="muted">上传到 C:\install\AI\Data\SoundEffects / BGM</span></div><div class="two-col"><div class="panel"><div class="panel-head"><h3>音效库</h3></div><p class="muted">支持环境、机械、脚步、爆炸、雨声、风声、门、车辆、城市分类。当前阶段只管理用户上传的音频。</p><input type="file" accept="audio/*" @change="uploadLibrary($event, false)"/><el-button link @click="loadAssets">查看已入库素材</el-button></div><div class="panel"><div class="panel-head"><h3>BGM 库</h3></div><p class="muted">剧集可绑定多条 BGM，最终通过 FFmpeg 混音，默认降低 BGM 音量保证人声优先。</p><input type="file" accept="audio/*" @change="uploadLibrary($event, true)"/></div></div></section>

      <section v-else-if="active === 'tasks'" class="page-content"><div class="toolbar"><div><div class="eyebrow">生成队列 / 历史</div><h2>任务中心</h2></div><el-button plain @click="loadTasks">刷新队列</el-button></div><div class="panel"><div class="queue-banner"><div><strong>GPU 串行保护已启用</strong><span>RTX 4070 12GB · 大模型任务并发 1 · 失败自动重试最多 2 次</span></div><el-tag type="warning">{{ tasks.filter(x => x.status === 'Running').length }} Running</el-tag></div><el-table :data="tasks" class="dark-table" stripe><el-table-column prop="id" label="#" width="75"/><el-table-column label="任务" min-width="210"><template #default="scope"><strong>{{ taskTypeLabel(scope.row.taskType) }}</strong><small class="table-sub">{{ scope.row.projectName || '未关联项目' }} · {{ scope.row.shotTitle || '独立任务' }}</small></template></el-table-column><el-table-column label="状态" width="110"><template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column><el-table-column label="失败原因" width="150"><template #default="scope">{{ scope.row.errorType || '-' }}</template></el-table-column><el-table-column label="GPU 峰值" width="130"><template #default="scope">{{ scope.row.vramPeakMiB ? `${scope.row.vramPeakMiB} MiB` : '-' }}</template></el-table-column><el-table-column label="耗时" width="110"><template #default="scope">{{ scope.row.durationMs ? `${(scope.row.durationMs / 1000).toFixed(1)}s` : '-' }}</template></el-table-column><el-table-column label="创建时间" width="180"><template #default="scope">{{ formatDate(scope.row.createdAt) }}</template></el-table-column><el-table-column label="操作" width="220" fixed="right"><template #default="scope"><el-button v-if="['Pending','Running'].includes(scope.row.status)" size="small" type="danger" text @click="taskAction(scope.row.id, 'cancel')">取消</el-button><el-button v-if="scope.row.status === 'Failed'" size="small" type="warning" text @click="taskAction(scope.row.id, 'retry')">重试</el-button><el-button v-if="['Succeeded','Failed','Cancelled'].includes(scope.row.status)" size="small" text @click="taskAction(scope.row.id, 'rerun')">重跑</el-button></template></el-table-column></el-table><el-empty v-if="!tasks.length" description="暂无任务，去项目制作台生成第一个镜头" /></div></section>

      <section v-else-if="active === 'assets'" class="page-content"><div class="toolbar"><div><div class="eyebrow">本地素材库</div><h2>素材中心</h2></div><el-button plain @click="loadAssets">刷新素材</el-button></div><div class="asset-grid media-grid"><article v-for="asset in assets" :key="asset.id" class="media-card"><div class="media-preview"><video v-if="isVideo(asset.path)" :src="mediaUrl(asset.path)" controls preload="metadata"></video><img v-else :src="mediaUrl(asset.path)" /></div><div class="media-info"><strong>{{ asset.name }}</strong><span>{{ assetTypeLabel(asset.assetType) }} · {{ formatBytes(asset.sizeBytes) }}</span><small>{{ asset.width || '-' }}×{{ asset.height || '-' }} · {{ asset.durationSeconds ? `${Number(asset.durationSeconds).toFixed(2)}s` : '静态' }}</small></div></article><div v-if="!assets.length" class="empty-board"><span>▤</span><p>生成后的图片、视频与最终输出会自动登记到素材库</p></div></div></section>

      <section v-else-if="active === 'workflows'" class="page-content"><div class="toolbar"><div><div class="eyebrow">ComfyUI 目录</div><h2>工作流与模型</h2></div><el-button type="primary" plain @click="scanWorkflows">扫描现有目录</el-button></div><div class="two-col"><div class="panel"><div class="panel-head"><div><h3>工作流</h3><span class="muted">{{ workflows.length }} 个 JSON 工作流</span></div></div><el-table :data="workflows" class="dark-table" size="small"><el-table-column prop="name" label="名称" min-width="210"/><el-table-column prop="workflowType" label="类型" width="130"><template #default="scope"><el-tag size="small" type="info">{{ workflowTypeLabel(scope.row.workflowType) }}</el-tag></template></el-table-column><el-table-column prop="modelName" label="模型" min-width="180"/><el-table-column label="契约准入" width="170"><template #default="scope"><el-tag size="small" :type="workflowContractType(workflowContractFor(scope.row))">{{ workflowContractLabel(workflowContractFor(scope.row)) }}</el-tag></template></el-table-column><el-table-column label="路径" min-width="250"><template #default="scope"><span class="path-text">{{ scope.row.path }}</span></template></el-table-column></el-table></div><div class="panel"><div class="panel-head"><div><h3>模型资产</h3><span class="muted">{{ models.length }} 个文件</span></div></div><el-table :data="models" class="dark-table" size="small"><el-table-column prop="name" label="文件" min-width="200"/><el-table-column label="类型" width="110"><template #default="scope">{{ modelTypeLabel(scope.row.modelType) }}</template></el-table-column><el-table-column label="大小" width="100"><template #default="scope">{{ formatBytes(scope.row.fileSizeBytes) }}</template></el-table-column></el-table></div></div></section>

      <section v-else-if="active === 'system'" class="page-content"><div class="toolbar"><div><div class="eyebrow">本地运行 / 诊断</div><h2>系统设置</h2></div><el-button plain @click="loadSystem">重新诊断</el-button></div><div class="system-grid"><div class="panel"><div class="panel-head"><h3>连接状态</h3></div><div class="check-list"><div><span>MySQL 8</span><el-tag :type="health?.database?.online ? 'success' : 'danger'">{{ health?.database?.online ? '在线' : '待配置凭据' }}</el-tag></div><div><span>ComfyUI API</span><el-tag :type="health?.comfy?.online ? 'success' : 'danger'">{{ health?.comfy?.online ? '在线' : '离线' }}</el-tag></div><div><span>FFmpeg / FFprobe</span><el-tag :type="health?.ffmpeg?.available ? 'success' : 'danger'">{{ health?.ffmpeg?.available ? '可用' : '缺失' }}</el-tag></div><div><span>监听地址</span><code>127.0.0.1:18080</code></div></div></div><div class="panel"><div class="panel-head"><h3>路径策略</h3></div><div class="path-list"><div><span>VideoStudio</span><code>{{ settings?.root || 'C:\\install\\AI\\VideoStudio' }}</code></div><div><span>数据</span><code>{{ settings?.data || 'C:\\install\\AI\\Data' }}</code></div><div><span>模型</span><code>{{ settings?.models || 'C:\\install\\AI\\Models' }}</code></div><div><span>工作流</span><code>{{ settings?.workflows || 'C:\\install\\AI\\Workflows' }}</code></div></div></div><div class="panel system-note"><div class="eyebrow">操作指南</div><h3>长期使用建议</h3><p>把角色身份锚点、场景主图和固定提示词先存入资产库，再从项目镜头提交任务。视频任务始终串行执行，避免 12GB 显存被多个大模型同时占用。</p><p>数据库密码只从 <code>config\local.env</code> 读取，不写入源码、前端或日志。</p></div></div></section>
      <div v-if="active === 'workflows'" class="panel" style="margin: 0 24px 24px"><div class="panel-head"><div><h3>质量预设</h3><span class="muted">新镜头会优先使用已验证的稳定路线</span></div><el-tag type="success">默认：I2V_SubtleMotion_v3</el-tag></div><el-table :data="presets.filter(item => ['ImageToVideo','Enhancement'].includes(item.presetType))" class="dark-table" size="small"><el-table-column prop="name" label="预设" min-width="210"/><el-table-column prop="presetType" label="类型" width="120"/><el-table-column prop="description" label="用途" min-width="360"/></el-table><p class="muted">人物默认：3 秒、320×416、24 FPS、guide 0.45、锁定镜头；5 秒转头只作为实验档，必须先通过 3 秒预检。</p></div>
      <section v-if="selectedEpisode && episodeOutput" class="panel episode-quality-gate-panel">
        <div class="panel-head"><div><div class="eyebrow">Episode 发布门禁</div><h3>正式成片状态</h3></div><el-tag :type="episodeOutput.canRender ? 'success' : 'warning'">{{ episodeOutput.canRender ? '可以正式合成' : '正式合成已阻断' }}</el-tag></div>
        <div class="quality-gate-summary"><span>镜头 QA {{ episodeOutput.qualityGate?.passedShotCount || 0 }}/{{ episodeOutput.qualityGate?.shotCount || 0 }}</span><span>Episode {{ episodeOutput.qualityGate?.episodeApproved ? 'Approved' : '未 Approved' }}</span><span>正式源 {{ episodeOutput.qualityGate?.sources?.filter(item => item.formalReady).length || 0 }}/{{ episodeOutput.qualityGate?.shotCount || 0 }}</span><span>发布技术 {{ releaseStatusLabel(episodeOutput.releaseEligibility?.technicalStatus) }}</span><span>发布内容 {{ releaseStatusLabel(episodeOutput.releaseEligibility?.contentStatus) }}</span></div>
        <p class="muted">{{ episodeOutput.formalBlockedReason || '质量门禁已满足；正式成片将只使用正式增强视频。' }}</p>
        <el-button v-if="episodeOutput.canPreview && !episodeOutput.canRender" type="primary" plain @click="queueEpisodePreview" :disabled="Boolean(episodeOutput.activeTask)">生成审核预览（不作为正式成片）</el-button>
        <el-button v-if="episodeOutput.canRender" type="success" @click="queueFormalEpisodeRender" :disabled="Boolean(episodeOutput.activeTask)">{{ latestEpisodeOutputVersion ? '重新合成正式成片' : '生成正式成片' }}</el-button>
      </section>
    </main>

    <input id="reference-input" type="file" accept="image/*" hidden @change="onReferenceFile" />
    <el-dialog v-model="referenceUploadDialog" title="归档阶段参考图" width="560px"><el-alert title="阶段参考只记录资产版本，不会自动切换模型或绕过人工审核。" type="info" :closable="false" show-icon /><el-form label-position="top" style="margin-top:16px"><div class="form-row"><el-form-item label="资产阶段"><el-select v-model="referenceUploadMeta.stage"><el-option label="基础状态" value="base"/><el-option label="服装变化" value="outfit-change"/><el-option label="受伤 / 状态变化" value="injured"/><el-option label="战斗后" value="battle-worn"/><el-option label="时间 / 光线变化" value="time-shift"/></el-select></el-form-item><el-form-item label="参考图用途"><el-select v-model="referenceUploadMeta.role"><el-option label="身份" value="identity"/><el-option label="服装" value="outfit"/><el-option label="姿态" value="pose"/><el-option label="环境" value="environment"/><el-option label="构图" value="composition"/></el-select></el-form-item></div><el-form-item label="阶段变更说明"><el-input v-model="referenceUploadMeta.changeReason" type="textarea" :rows="3" placeholder="例如：角色在第 3 集受伤，改穿病号服；留空也可以。" /></el-form-item></el-form><template #footer><el-button @click="referenceUploadDialog = false">取消</el-button><el-button type="primary" @click="document.querySelector('#reference-input').click()">选择图片</el-button></template></el-dialog>
    <el-dialog v-model="characterReviewDialog" :title="`审核角色参考图 · ${characterReviewTarget?.name || ''}`" width="760px">
      <div v-loading="characterReferencesLoading" class="reference-review-list">
        <div v-for="reference in characterReferences" :key="reference.id" class="reference-review-row">
          <img v-if="reference.mediaUrl || reference.assetPath" :src="reference.mediaUrl || mediaUrl(reference.assetPath)" />
          <div class="reference-review-meta"><strong>{{ reference.stage || 'base' }} · {{ reference.role || reference.kind || 'identity' }} · {{ reference.isAnchor ? '身份锚点' : '普通参考' }}</strong><span>{{ reference.width || '-' }}×{{ reference.height || '-' }} · V{{ reference.assetVersion || 1 }} · {{ reference.available ? '文件可用' : '文件缺失' }}</span><small v-if="reference.changeReason" class="muted">{{ reference.changeReason }}</small><el-tag size="small" :type="statusType(reference.reviewStatus)">{{ statusLabel(reference.reviewStatus) }}</el-tag></div>
          <div class="reference-review-actions"><el-button size="small" type="success" plain @click="reviewCharacterReference(reference, 'Approved')">通过</el-button><el-button size="small" type="warning" plain @click="reviewCharacterReference(reference, 'NeedReview')">待复核</el-button><el-button size="small" type="danger" plain @click="reviewCharacterReference(reference, 'Rejected')">拒绝</el-button></div>
        </div>
        <el-empty v-if="!characterReferences.length && !characterReferencesLoading" description="该角色还没有参考图" />
      </div>
      <template #footer><span class="muted">只有人工 Approved 的身份参考图才可作为正式角色锚点。</span><el-button @click="characterReviewDialog = false">关闭</el-button></template>
    </el-dialog>
    <el-dialog v-model="projectDialog" :title="projectForm.id ? '编辑项目' : '新建项目'" width="620px"><el-form label-position="top"><el-form-item label="项目名称"><el-input v-model="projectForm.name" placeholder="例如：末日科幻列车" /></el-form-item><el-form-item label="简介"><el-input v-model="projectForm.description" type="textarea" :rows="4" placeholder="项目主题、风格和制作目标" /></el-form-item><div class="form-row"><el-form-item label="画面比例"><el-select v-model="projectForm.aspectRatio"><el-option label="横屏 16:9" value="16:9"/><el-option label="竖屏 9:16" value="9:16"/><el-option label="方形 1:1" value="1:1"/></el-select></el-form-item><el-form-item label="默认 FPS"><el-input-number v-model="projectForm.defaultFps" :min="24" :max="60"/></el-form-item><el-form-item label="状态"><el-select v-model="projectForm.status"><el-option label="制作中" value="Active"/><el-option label="暂停" value="Paused"/><el-option label="归档" value="Archived"/></el-select></el-form-item></div><div class="form-row"><el-form-item label="默认宽"><el-input-number v-model="projectForm.defaultWidth" :min="256" :step="64"/></el-form-item><el-form-item label="默认高"><el-input-number v-model="projectForm.defaultHeight" :min="256" :step="64"/></el-form-item><el-form-item label="风格"><el-input v-model="projectForm.style" placeholder="电影感、写实风格"/></el-form-item></div><el-form-item label="提示词 风格"><el-input v-model="projectForm.promptStyle" placeholder="真实、动作克制、身份一致"/></el-form-item></el-form><template #footer><el-button @click="projectDialog = false">取消</el-button><el-button type="primary" @click="saveProject">保存项目</el-button></template></el-dialog>
    <el-dialog v-model="episodeDialog" title="新建一集" width="560px"><el-form label-position="top"><div class="form-row"><el-form-item label="集数"><el-input-number v-model="episodeForm.episodeNumber" :min="1"/></el-form-item><el-form-item label="目标时长（秒）"><el-input-number v-model="episodeForm.targetSeconds" :min="1"/></el-form-item><el-form-item label="输出帧率"><el-input-number v-model="episodeForm.outputFps" :min="24" :max="60"/></el-form-item></div><el-form-item label="集名称"><el-input v-model="episodeForm.name"/></el-form-item><el-form-item label="制作备注"><el-input v-model="episodeForm.description" type="textarea" :rows="3"/></el-form-item></el-form><template #footer><el-button @click="episodeDialog = false">取消</el-button><el-button type="primary" @click="saveEpisode">创建本集</el-button></template></el-dialog>
    <el-dialog v-model="shotDialog" title="添加镜头" width="720px"><el-form label-position="top"><div class="form-row"><el-form-item label="镜头号"><el-input-number v-model="shotForm.shotNumber" :min="1"/></el-form-item><el-form-item label="宽"><el-input-number v-model="shotForm.width" :min="256" :step="64"/></el-form-item><el-form-item label="高"><el-input-number v-model="shotForm.height" :min="256" :step="64"/></el-form-item><el-form-item label="帧数"><el-input-number v-model="shotForm.frames" :min="25" :max="241"/></el-form-item></div><el-form-item label="镜头标题"><el-input v-model="shotForm.title"/></el-form-item><el-form-item label="正向提示词"><el-input v-model="shotForm.prompt" type="textarea" :rows="3" placeholder="人物、动作、场景、光线和电影镜头语言"/></el-form-item><el-form-item label="视频工作流"><el-select v-model="shotForm.workflowId" clearable placeholder="Wan2.2 质量优先；留空使用质量优先默认路线" @change="applyWorkflowDefaults"><el-option v-for="workflow in videoWorkflows" :key="workflow.id" :label="workflow.name + ' · ' + (workflow.modelName || '模型待定')" :value="workflow.id"/></el-select><small class="muted">默认优先 Wan2.2：首测 49 帧；竖图自动匹配 320×416，横图匹配 512×320。稳定后再提高帧数或分辨率。</small></el-form-item><el-form-item label="输入参考图（图生视频）"><el-input v-model="shotForm.inputImagePath" placeholder="C:\\install\\AI\\Data\\Images\\keyframe.png" @change="applyInputAspectDefaults"/></el-form-item><div class="form-row"><el-form-item label="镜头预设"><el-input v-model="shotForm.cameraPreset"/></el-form-item><el-form-item label="动作预设"><el-input v-model="shotForm.motionPreset"/></el-form-item><el-form-item label="随机种子"><el-input-number v-model="shotForm.seed" :min="0"/></el-form-item></div><el-form-item label="负面提示词"><el-input v-model="shotForm.negativePrompt" type="textarea" :rows="2"/></el-form-item></el-form><template #footer><el-button @click="shotDialog = false">取消</el-button><el-button type="primary" @click="saveShot">保存镜头</el-button></template></el-dialog>
    <el-dialog v-model="characterDialog" :title="characterForm.id ? '编辑角色资产' : '新建角色资产'" width="720px"><el-form label-position="top"><div class="form-row"><el-form-item label="角色名"><el-input v-model="characterForm.name"/></el-form-item><el-form-item label="年龄设定"><el-input v-model="characterForm.ageSetting"/></el-form-item><el-form-item label="身体比例"><el-input v-model="characterForm.bodyRatio"/></el-form-item></div><el-form-item label="脸部特征"><el-input v-model="characterForm.faceFeatures" type="textarea" :rows="2" placeholder="脸型、眼睛、鼻子、肤质等固定特征"/></el-form-item><el-form-item label="发型"><el-input v-model="characterForm.hair"/></el-form-item><el-form-item label="服装"><el-input v-model="characterForm.clothes"/></el-form-item><div class="form-row"><el-form-item label="默认音色 ID"><el-input v-model="characterForm.voiceId" placeholder="留空使用系统中文默认音色"/></el-form-item><el-form-item label="语速"><el-input-number v-model="characterForm.voiceSpeed" :min="0.5" :max="2" :step="0.1"/></el-form-item><el-form-item label="音高"><el-input-number v-model="characterForm.voicePitch" :min="-10" :max="10"/></el-form-item></div><el-form-item label="固定提示词"><el-input v-model="characterForm.fixedPrompt" type="textarea" :rows="3"/></el-form-item><el-form-item label="负面提示词"><el-input v-model="characterForm.negativePrompt" type="textarea" :rows="2"/></el-form-item></el-form><template #footer><el-button @click="characterDialog = false">取消</el-button><el-button type="primary" @click="saveCharacter">保存角色</el-button></template></el-dialog>
    <el-dialog v-model="sceneDialog" :title="sceneForm.id ? '编辑场景资产' : '新建场景资产'" width="680px"><el-form label-position="top"><el-form-item label="场景名"><el-input v-model="sceneForm.name"/></el-form-item><el-form-item label="场景说明"><el-input v-model="sceneForm.description" type="textarea" :rows="3"/></el-form-item><el-form-item label="固定提示词"><el-input v-model="sceneForm.fixedPrompt" type="textarea" :rows="3"/></el-form-item><el-form-item label="风格"><el-input v-model="sceneForm.style" placeholder="电影感、写实风格"/></el-form-item><el-form-item label="负面提示词"><el-input v-model="sceneForm.negativePrompt" type="textarea" :rows="2"/></el-form-item></el-form><template #footer><el-button @click="sceneDialog = false">取消</el-button><el-button type="primary" @click="saveScene">保存场景</el-button></template></el-dialog>
    <el-dialog v-model="scriptDialog" :title="scriptForm.id ? '编辑剧本并生成新版本' : '新建剧本'" width="820px"><el-form label-position="top"><div class="form-row"><el-form-item label="项目"><el-select v-model="scriptForm.projectId" placeholder="选择项目"><el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id"/></el-select></el-form-item><el-form-item label="Episode"><el-select v-model="scriptForm.episodeId" clearable placeholder="选择 Episode"><el-option v-for="episode in episodes" :key="episode.id" :label="episode.name" :value="episode.id"/></el-select></el-form-item></div><el-form-item label="剧本标题"><el-input v-model="scriptForm.title"/></el-form-item><el-form-item label="TXT / Markdown 剧本内容"><el-input v-model="scriptForm.content" type="textarea" :rows="16" placeholder="场景 1：末日列车驾驶室，夜晚，雨声。&#10;林雪：列车还在运行。&#10;陈默握紧扶手，转头看向窗外。&#10;&#10;场景 2：车厢，中景，陈默向林雪挥手。"/></el-form-item></el-form><template #footer><el-button @click="scriptDialog = false">取消</el-button><el-button type="primary" @click="saveScript">保存剧本</el-button></template></el-dialog>
    <el-dialog v-model="candidateDialog" :title="`选择镜头 ${candidateShot?.shotNumber || ''} 的关键帧`" width="900px"><div class="candidate-grid"><button v-for="candidate in candidateOptions" :key="candidate.id" type="button" class="candidate-card" @click="confirmCandidate(candidate)"><img v-if="candidate.path" :src="mediaUrl(candidate.path)" /><div><strong>候选 {{ candidate.candidateIndex || candidate.id }}</strong><span>{{ candidate.qcStatus || '待验收' }} · {{ candidate.qualityScore ? Number(candidate.qualityScore).toFixed(0) : '-' }}</span></div></button><el-empty v-if="!candidateOptions.length" description="暂无关键帧候选" /></div><template #footer><el-button @click="candidateDialog = false">取消</el-button></template></el-dialog>
    <el-dialog v-model="takeDialog" :title="`镜头 ${takeShot?.shotNumber || ''} 的 TAKE / 版本`" width="900px">
      <div v-loading="takesLoading" class="candidate-grid take-grid">
        <div v-for="take in takeOptions" :key="take.id" class="candidate-card take-card">
          <video v-if="take.mediaUrl && isVideo(take.assetPath || '')" :src="take.mediaUrl" controls preload="metadata" />
          <img v-else-if="take.mediaUrl" :src="take.mediaUrl" />
          <div><strong>TAKE {{ take.candidateIndex || take.id }}</strong><span>{{ take.taskType || '视频' }} · {{ statusLabel(take.status) }} · {{ formatDate(take.createdAt) }}</span><small>{{ take.available ? `${take.width || '-'}×${take.height || '-'} · ${formatDuration(take.durationSeconds)}` : '文件尚未在受控媒体目录中找到' }}</small></div>
        </div>
        <el-empty v-if="!takeOptions.length && !takesLoading" description="该镜头暂无视频版本" />
      </div>
      <template #footer><span class="muted">版本查看为只读；正式使用仍需经过镜头审核与整集发布门禁。</span><el-button @click="takeDialog = false">关闭</el-button></template>
    </el-dialog>
    <el-dialog v-model="episodeOutputDialog" class="episode-output-dialog" width="1100px" top="5vh" destroy-on-close>
      <template #header><div class="episode-dialog-title"><div><div class="eyebrow">正式 Episode 输出</div><strong>{{ selectedEpisode?.name || '整集成片' }}</strong></div><el-tag v-if="selectedEpisodeOutputVersion" :type="statusType(selectedEpisodeOutputVersion.status)">V{{ selectedEpisodeOutputVersion.version }} · {{ statusLabel(selectedEpisodeOutputVersion.status) }}</el-tag><el-tag v-else type="info">暂无正式成片</el-tag></div></template>
      <div class="episode-output-dialog-grid">
        <section class="episode-result-stage">
          <template v-if="selectedEpisodeOutputVersion?.exists && selectedEpisodeOutputVersion.outputPath">
            <video :key="selectedEpisodeOutputVersion.taskId || selectedEpisodeOutputVersion.outputPath" class="episode-result-player" :src="mediaUrl(selectedEpisodeOutputVersion.outputPath)" controls preload="metadata"></video>
            <div class="episode-result-details"><span>实际 {{ selectedEpisodeOutputVersion.actual?.width || '-' }}×{{ selectedEpisodeOutputVersion.actual?.height || '-' }}</span><span>{{ selectedEpisodeOutputVersion.actual?.fps ? Number(selectedEpisodeOutputVersion.actual.fps).toFixed(2) : '-' }} FPS</span><span>{{ formatDuration(selectedEpisodeOutputVersion.actual?.durationSeconds) }}</span><span :class="selectedEpisodeOutputVersion.actual?.hasAudio ? 'audio-ok' : 'audio-missing'">音频 {{ selectedEpisodeOutputVersion.actual?.hasAudio ? '已包含' : '缺失' }}</span><span v-if="selectedEpisodeOutputVersion.actual?.codec">{{ selectedEpisodeOutputVersion.actual.codec }}</span><span v-if="selectedEpisodeOutputVersion.actual?.sizeBytes">{{ formatBytes(selectedEpisodeOutputVersion.actual.sizeBytes) }}</span></div>
            <div class="episode-output-note">目标 {{ episodeOutput?.target?.width || selectedEpisode?.outputWidth }}×{{ episodeOutput?.target?.height || selectedEpisode?.outputHeight }} · {{ episodeOutput?.target?.fps || selectedEpisode?.outputFps }} FPS · 成片信息来自最终文件探测</div>
            <div v-if="selectedEpisodeOutputVersion.sourceSnapshot?.length" class="episode-source-snapshot"><strong>本次合成镜头快照</strong><div><span v-for="shot in selectedEpisodeOutputVersion.sourceSnapshot" :key="`${selectedEpisodeOutputVersion.taskId}-${shot.shotId}`">S{{ String(shot.shotNumber).padStart(2, '0') }} {{ shot.title }}</span></div></div>
          </template>
          <el-empty v-else :description="selectedEpisodeOutputVersion?.status === 'Failed' ? `V${selectedEpisodeOutputVersion.version} 合成失败：${selectedEpisodeOutputVersion.errorMessage || '请重新合成'}` : (episodeOutput?.renderBlockedReason || '当前还没有正式成片，完成所有镜头正式视频后即可生成整集成片。')" :image-size="90"/>
        </section>
        <aside class="episode-version-list"><div class="panel-head"><div><strong>成片版本</strong><small>{{ episodeOutputVersions.length }} 条合成记录</small></div></div><button v-for="version in episodeOutputVersions" :key="version.taskId" class="episode-version-row" :class="{ selected: String(selectedEpisodeOutputTaskId) === String(version.taskId) || (!selectedEpisodeOutputTaskId && latestEpisodeOutputVersion?.taskId === version.taskId) }" @click="selectedEpisodeOutputTaskId = version.taskId"><div><strong>V{{ version.version }}</strong><small>{{ formatDate(version.finishedAt || version.createdAt) }}</small></div><div><el-tag size="small" :type="statusType(version.status)">{{ statusLabel(version.status) }}</el-tag><small v-if="version.status === 'Running'">{{ Math.round(Number(version.progress || 0) * 100) }}%</small></div></button><el-empty v-if="!episodeOutputVersions.length" description="暂无历史版本" :image-size="50"/></aside>
      </div>
      <template #footer><el-button @click="episodeOutputDialog = false">关闭</el-button><el-button v-if="selectedEpisodeOutputVersion?.exists" plain @click="downloadEpisodeOutput">下载成片</el-button><el-button type="success" @click="queueFormalEpisodeRender" :disabled="!episodeOutput?.canRender || Boolean(episodeOutput?.activeTask)">{{ latestEpisodeOutputVersion ? '重新合成' : '生成整集成片' }}</el-button></template>
    </el-dialog>
  </div>
    <section v-if="active === 'qa' && qaDetail" class="panel release-candidate-panel">
      <div class="panel-head"><div><div class="eyebrow">发布候选包</div><h3>显式选择要导出的版本</h3><span class="muted">导出不会自动使用历史 Ready 候选；每个版本绑定整片、镜头、字幕、音频、封面、审核版本和文件哈希。</span></div><div class="release-candidate-toolbar"><el-button plain @click="openReleaseCandidateDialog">创建候选包</el-button><el-button type="warning" plain @click="exportQaEpisode" :disabled="!qaDetail.episode.qaLocked">选择 Ready 版本导出</el-button></div></div>
      <el-alert v-if="releaseCandidatesError" :title="releaseCandidatesError" type="warning" :closable="false" show-icon />
      <el-table v-loading="releaseCandidatesLoading" :data="releaseCandidates" class="dark-table release-candidate-table" stripe>
        <el-table-column prop="version" label="版本" width="80"><template #default="scope">V{{ scope.row.version }}</template></el-table-column>
        <el-table-column label="状态" width="125"><template #default="scope"><el-tag size="small" :type="scope.row.status === 'Ready' ? 'success' : scope.row.status === 'Expired' ? 'warning' : 'info'">{{ scope.row.status || '未设置' }}</el-tag></template></el-table-column>
        <el-table-column label="门禁" width="125"><template #default="scope">{{ releaseStatusLabel(scope.row.releaseEligibility) }}</template></el-table-column>
        <el-table-column label="来源快照哈希" min-width="300"><template #default="scope"><code>{{ scope.row.sourceManifestSha256 || '-' }}</code></template></el-table-column>
        <el-table-column label="导出任务" width="110"><template #default="scope">{{ scope.row.exportTaskId || '-' }}</template></el-table-column>
        <el-table-column label="创建时间" width="180"><template #default="scope">{{ formatDate(scope.row.createdAt) }}</template></el-table-column>
      </el-table>
    </section>
    <el-dialog v-model="releaseCandidateDialog" title="创建发布候选包" width="820px">
      <el-alert title="所有字段都必须是真实可追溯证据；勾选不能覆盖待核实许可证、缺少 AI 披露或未通过的镜头门禁。" type="warning" :closable="false" show-icon />
      <el-form label-position="top" style="margin-top:16px">
        <el-form-item label="许可证据确认"><el-checkbox v-model="releaseCandidateForm.licenseEvidenceConfirmed">我已核对具体模型、权重版本、素材范围和适用发布范围</el-checkbox></el-form-item>
        <el-form-item label="许可证据说明"><el-input v-model="releaseCandidateForm.licenseReference" type="textarea" :rows="3" placeholder="许可证文件/订单/条款编号、核对日期和适用条件" /></el-form-item>
        <div class="form-row"><el-form-item label="适用范围"><el-input v-model="releaseCandidateForm.licenseScope" placeholder="模型、素材与本集的具体用途" /></el-form-item><el-form-item label="地域"><el-input v-model="releaseCandidateForm.licenseTerritory" placeholder="例如：中国大陆 / 全球（需有依据）" /></el-form-item><el-form-item label="平台"><el-input v-model="releaseCandidateForm.licensePlatforms" placeholder="例如：内部验收 / 指定平台" /></el-form-item></div>
        <el-form-item label="具体模型与权重哈希"><el-input v-model="releaseCandidateForm.licenseModels" type="textarea" :rows="4" placeholder="每行填写模型文件名和实际权重 SHA-256" /></el-form-item>
        <el-form-item label="素材版本 / 哈希绑定"><el-input v-model="releaseCandidateForm.assetVersionBinding" type="textarea" :rows="3" placeholder="必须包含页面显示的 sourceManifestSha256，以及适用的素材版本说明" /></el-form-item>
        <el-form-item label="AI 内容披露"><el-checkbox v-model="releaseCandidateForm.aiDisclosureRecorded">已准备与交付物对应的 AI 生成披露</el-checkbox><el-input v-model="releaseCandidateForm.aiDisclosure" type="textarea" :rows="3" placeholder="实际对外披露文本，不能只写‘AI生成’复选框" style="margin-top:8px" /></el-form-item>
        <el-form-item label="披露交付文件路径"><el-input v-model="releaseCandidateForm.aiDisclosurePath" placeholder="受控目录内的实际披露文件，例如 Data\Release\episode-ai-disclosure.txt" /></el-form-item>
        <el-form-item label="候选包备注"><el-input v-model="releaseCandidateForm.note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="releaseCandidateDialog = false">取消</el-button><el-button type="primary" :loading="releaseCandidateCreating" @click="createReleaseCandidate">保存并重新评估</el-button></template>
    </el-dialog>
    <el-dialog v-model="releaseExportDialog" title="选择发布候选版本" width="680px">
      <el-alert title="导出任务只会使用下方明确选择的候选包；排队、开始执行和落盘后都会再次核对版本与文件哈希。" type="info" :closable="false" show-icon />
      <el-form label-position="top" style="margin-top:16px"><el-form-item label="Ready 候选包"><el-select v-model="releaseExportCandidateId" style="width:100%"><el-option v-for="candidate in readyReleaseCandidates" :key="candidate.id" :label="`V${candidate.version} · ${candidate.sourceManifestSha256 || '无快照哈希'} · 创建于 ${formatDate(candidate.createdAt)}`" :value="candidate.id" /></el-select></el-form-item></el-form>
      <template #footer><el-button @click="releaseExportDialog = false">取消</el-button><el-button type="warning" :loading="releaseExporting" @click="confirmReleaseExport">确认导出此版本</el-button></template>
    </el-dialog>
</template>
