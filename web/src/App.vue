<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const active = ref('dashboard')
const loading = ref(false)
const errorText = ref('')
const health = ref(null)
const settings = ref(null)
const dashboard = reactive({ counts: {}, recentTasks: [], comfy: null })
const projects = ref([])
const characters = ref([])
const scenes = ref([])
const workflows = ref([])
const models = ref([])
const tasks = ref([])
const assets = ref([])
const scripts = ref([])
const selectedScript = ref(null)
const analysisResult = ref(null)
const productionStatus = ref(null)
const voices = ref({ available: false, voices: [] })
const selectedProject = ref(null)
const episodes = ref([])
const shots = ref([])
const selectedEpisode = ref(null)
const qaEpisodes = ref([])
const qaSelectedEpisode = ref(null)
const qaDetail = ref(null)
const qaPreset = ref('Standard')

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
const ttsForm = reactive({ text: '', voiceId: '', speed: 1, pitch: 0 })
const referenceFile = ref(null)
const referenceTarget = ref(null)

const navItems = [
  { id: 'dashboard', label: '总览', icon: '⌂', hint: '运行状态与最近任务' },
  { id: 'projects', label: '项目制作', icon: '▣', hint: '剧集、镜头与批量生成' },
  { id: 'characters', label: '角色资产', icon: '◎', hint: '身份锚点与参考图' },
  { id: 'scenes', label: '场景资产', icon: '◇', hint: '场景主图与固定提示词' },
  { id: 'scripts', label: '剧本拆分', icon: '✎', hint: '剧本、人物/场景识别与分镜' },
  { id: 'production', label: '生产中心', icon: '▶', hint: '关键帧、视频、QC 与合成' },
  { id: 'qa', label: '质量验收', icon: '✓', hint: '技术、镜头与 Episode 发布验收' },
  { id: 'voice', label: '声音', icon: '♫', hint: '本地 TTS、旁白与对白' },
  { id: 'sfx', label: '音效 / BGM', icon: '◈', hint: '本地音效库与背景音乐' },
  { id: 'tasks', label: '任务中心', icon: '↯', hint: '队列、重试、取消与历史' },
  { id: 'assets', label: '素材中心', icon: '▤', hint: '图片、视频、音频与输出' },
  { id: 'workflows', label: '工作流与模型', icon: '⌘', hint: '扫描 ComfyUI 工作流' },
  { id: 'system', label: '系统设置', icon: '⚙', hint: '路径、GPU 与连接诊断' }
]

const currentNav = computed(() => navItems.find(x => x.id === active.value) || navItems[0])
const online = computed(() => health.value?.database?.online && health.value?.comfy?.online)
const gpuText = computed(() => {
  const gpu = health.value?.comfy?.gpu
  if (!gpu) return 'GPU 状态未知'
  return `${gpu.name || 'CUDA'} · ${gpu.freeMiB || 0}/${gpu.totalMiB || 0} MiB 空闲`
})

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (!(options.body instanceof FormData) && !headers['Content-Type']) headers['Content-Type'] = 'application/json'
  const response = await fetch(path, { ...options, headers })
  const text = await response.text()
  let data = {}
  try { data = text ? JSON.parse(text) : {} } catch { data = { raw: text } }
  if (!response.ok) throw new Error(data.error || data.raw || `请求失败 HTTP ${response.status}`)
  return data
}

async function refreshHealth() {
  try { health.value = await api('/api/health'); errorText.value = '' } catch (error) { errorText.value = error.message }
}

async function loadDashboard() {
  await refreshHealth()
  try { Object.assign(dashboard, await api('/api/dashboard')) } catch (error) { errorText.value = error.message }
}

async function loadProjects() {
  projects.value = await api('/api/projects')
  if (selectedProject.value) {
    const found = projects.value.find(x => x.id === selectedProject.value.id)
    if (found) await selectProject(found)
  }
}

async function selectProject(project) {
  selectedProject.value = project
  episodes.value = await api(`/api/projects/${project.id}/episodes`)
  selectedEpisode.value = episodes.value[0] || null
  shots.value = selectedEpisode.value ? await api(`/api/episodes/${selectedEpisode.value.id}/shots`) : []
}

async function selectEpisode(episode) {
  selectedEpisode.value = episode
  shots.value = await api(`/api/episodes/${episode.id}/shots`)
}

async function loadCharacters() { characters.value = await api('/api/characters') }
async function loadScenes() { scenes.value = await api('/api/scenes') }
async function loadTasks() { tasks.value = await api('/api/tasks?limit=150') }
async function loadAssets() { assets.value = await api('/api/assets') }
async function loadScripts() { scripts.value = await api('/api/scripts') }
async function loadWorkflows() { workflows.value = await api('/api/workflows'); models.value = await api('/api/models') }
async function loadSystem() { await refreshHealth(); settings.value = await api('/api/system/settings') }
async function loadVoices() { voices.value = await api('/api/audio/voices') }
async function loadQaDetail() {
  if (!qaSelectedEpisode.value) { qaDetail.value = null; return }
  qaDetail.value = await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}`)
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
  try { const note = await ElMessageBox.prompt('可填写审核备注（可留空）', `${statusLabel(decision)} · ${shot.title}`, { inputValue: '' }); await api(`/api/qa/shots/${shot.id}/review`, { method: 'POST', body: JSON.stringify({ decision, reviewer: 'local-user', note: note.value }) }); ElMessage.success('镜头审核已保存'); await loadQa() } catch (error) { if (error !== 'cancel') ElMessage.error(error.message) }
}
async function reviewEpisodeQa(decision) {
  if (!qaSelectedEpisode.value) return
  try { const note = await ElMessageBox.prompt('可填写剧集审核备注（可留空）', `${statusLabel(decision)} · ${qaSelectedEpisode.value.name}`, { inputValue: '' }); await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/review`, { method: 'POST', body: JSON.stringify({ decision, reviewer: 'local-user', note: note.value }) }); ElMessage.success(`剧集已标记为 ${statusLabel(decision)}`); await loadQa() } catch (error) { if (error !== 'cancel') ElMessage.error(error.message) }
}
async function unlockQaEpisode() { try { await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/unlock`, { method: 'POST' }); ElMessage.success('剧集已解锁'); await loadQa() } catch (error) { ElMessage.error(error.message) } }
async function regenerateQaShot(shot) { try { await api(`/api/qa/shots/${shot.id}/regenerate`, { method: 'POST', body: JSON.stringify({ preset: qaPreset.value, autoRetry: true }) }); ElMessage.success('已提交 QA 定向重生成'); await loadQa() } catch (error) { ElMessage.error(error.message) } }
async function exportQaEpisode() { try { const result = await api(`/api/qa/episodes/${qaSelectedEpisode.value.id}/export`, { method: 'POST', body: JSON.stringify({ includeSubtitles: true, includeCover: true }) }); ElMessage.success(`主片导出任务已提交：${result.taskId}`); await loadQa() } catch (error) { ElMessage.error(error.message) } }

async function loadActive() {
  loading.value = true
  try {
    if (active.value === 'dashboard') await loadDashboard()
    if (active.value === 'projects') { await loadProjects(); await loadScenes(); await loadCharacters(); await loadWorkflows() }
    if (active.value === 'characters') await loadCharacters()
    if (active.value === 'scenes') await loadScenes()
    if (active.value === 'scripts') { await loadProjects(); await loadScripts() }
    if (active.value === 'production') { await loadProjects(); if (selectedProject.value) await selectProject(selectedProject.value); if (selectedEpisode.value) productionStatus.value = await api(`/api/production/status?episodeId=${selectedEpisode.value.id}`) }
    if (active.value === 'qa') await loadQa()
    if (active.value === 'voice') { await loadVoices(); await loadTasks() }
    if (active.value === 'sfx') await loadAssets()
    if (active.value === 'tasks') await loadTasks()
    if (active.value === 'assets') await loadAssets()
    if (active.value === 'workflows') await loadWorkflows()
    if (active.value === 'system') await loadSystem()
    errorText.value = ''
  } catch (error) { errorText.value = error.message }
  finally { loading.value = false }
}

watch(active, loadActive)
onMounted(loadActive)

function resetProject() { Object.assign(projectForm, { id: null, name: '', description: '', status: 'Active', aspectRatio: '16:9', style: '', defaultFps: 30, defaultWidth: 1920, defaultHeight: 1080, promptStyle: '', bgmPath: '', bgmVolume: 0.18 }); projectDialog.value = true }
function editProject(row) { Object.assign(projectForm, { id: row.id, name: row.name, description: row.description || '', status: row.status || 'Active', aspectRatio: row.aspectRatio || '16:9', style: row.style || '', defaultFps: row.defaultFps || 30, defaultWidth: row.defaultWidth || 1920, defaultHeight: row.defaultHeight || 1080, promptStyle: row.promptStyle || '', bgmPath: row.bgmPath || '', bgmVolume: row.bgmVolume || 0.18 }); projectDialog.value = true }
async function saveProject() {
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
  try { await api('/api/episodes', { method: 'POST', body: JSON.stringify(episodeForm) }); episodeDialog.value = false; await selectProject(selectedProject.value); ElMessage.success('集已创建') } catch (error) { ElMessage.error(error.message) }
}
function openShotDialog() {
  if (!selectedProject.value || !selectedEpisode.value) return ElMessage.warning('请先选择项目和集')
  Object.assign(shotForm, { id: null, projectId: selectedProject.value.id, episodeId: selectedEpisode.value.id, shotNumber: shots.value.length + 1, title: `镜头 ${String(shots.value.length + 1).padStart(2, '0')}`, sceneId: null, characterIds: [], prompt: '', negativePrompt: '低清晰度，畸形手，额外手指，闪烁，脸部变形，文字，水印', workflowId: null, seed: Math.floor(Math.random() * 900000000), width: 512, height: 320, frames: 121, fps: 24, inputImagePath: '', motionPreset: '电影感慢动作', cameraPreset: '中景', status: 'Draft' })
  shotDialog.value = true
}
async function saveShot() {
  try { await api('/api/shots', { method: 'POST', body: JSON.stringify(shotForm) }); shotDialog.value = false; await selectEpisode(selectedEpisode.value); ElMessage.success('镜头已保存') } catch (error) { ElMessage.error(error.message) }
}
async function queueShot(shot) {
  try {
    const data = { projectId: selectedProject.value?.id, episodeId: selectedEpisode.value?.id, shotId: shot.id, taskType: shot.inputImagePath ? 'ImageToVideo' : 'Image', workflowId: shot.workflowId, inputImagePath: shot.inputImagePath, maxRetries: 2, parameters: { positive: shot.prompt, negative: shot.negativePrompt, seed: shot.seed, width: shot.width || 512, height: shot.height || 320, frames: shot.frames || 121, fps: shot.fps || 24, cfg: 3 } }
    await api('/api/tasks', { method: 'POST', body: JSON.stringify(data) }); ElMessage.success(`镜头 ${shot.shotNumber} 已加入队列`); if (active.value === 'tasks') await loadTasks()
  } catch (error) { ElMessage.error(error.message) }
}
async function concatEpisode() { try { await api(`/api/episodes/${selectedEpisode.value.id}/concat`, { method: 'POST' }); ElMessage.success('拼接任务已加入队列') } catch (error) { ElMessage.error(error.message) } }

function resetCharacter() { Object.assign(characterForm, { id: null, projectId: selectedProject.value?.id || null, name: '', ageSetting: '', faceFeatures: '', hair: '', clothes: '', bodyRatio: '', fixedPrompt: '', negativePrompt: '', anchorPath: '', voiceId: '', voiceSpeed: 1, voicePitch: 0 }); characterDialog.value = true }
function editCharacter(row) { Object.assign(characterForm, row); characterDialog.value = true }
async function saveCharacter() { try { const method = characterForm.id ? 'PUT' : 'POST'; const path = characterForm.id ? `/api/characters/${characterForm.id}` : '/api/characters'; await api(path, { method, body: JSON.stringify(characterForm) }); characterDialog.value = false; await loadCharacters(); ElMessage.success('角色资产已保存') } catch (error) { ElMessage.error(error.message) } }
async function deleteCharacter(row) { try { await api(`/api/characters/${row.id}`, { method: 'DELETE' }); await loadCharacters(); ElMessage.success('角色已删除') } catch (error) { ElMessage.error(error.message) } }
function chooseReference(row) { referenceTarget.value = { type: 'character', id: row.id }; document.querySelector('#reference-input').click() }
function onReferenceFile(event) { referenceFile.value = event.target.files?.[0] || null; uploadReference() }
async function uploadReference() { if (!referenceFile.value || !referenceTarget.value) return; const form = new FormData(); form.append('file', referenceFile.value); form.append('kind', 'identity'); form.append('isAnchor', 'true'); try { await api(`/api/${referenceTarget.value.type === 'character' ? 'characters' : 'scenes'}/${referenceTarget.value.id}/references`, { method: 'POST', headers: {}, body: form }); ElMessage.success('参考图已归档'); referenceFile.value = null; await (referenceTarget.value.type === 'character' ? loadCharacters() : loadScenes()) } catch (error) { ElMessage.error(error.message) } }

function resetScene() { Object.assign(sceneForm, { id: null, projectId: selectedProject.value?.id || null, name: '', description: '', fixedPrompt: '', negativePrompt: '', style: '电影感、写实风格', anchorPath: '' }); sceneDialog.value = true }
function editScene(row) { Object.assign(sceneForm, row); sceneDialog.value = true }
async function saveScene() { try { const method = sceneForm.id ? 'PUT' : 'POST'; const path = sceneForm.id ? `/api/scenes/${sceneForm.id}` : '/api/scenes'; await api(path, { method, body: JSON.stringify(sceneForm) }); sceneDialog.value = false; await loadScenes(); ElMessage.success('场景资产已保存') } catch (error) { ElMessage.error(error.message) } }
async function deleteScene(row) { try { await api(`/api/scenes/${row.id}`, { method: 'DELETE' }); await loadScenes(); ElMessage.success('场景已删除') } catch (error) { ElMessage.error(error.message) } }
function chooseSceneReference(row) { referenceTarget.value = { type: 'scene', id: row.id }; document.querySelector('#reference-input').click() }

function resetScript() { Object.assign(scriptForm, { id: null, projectId: selectedProject.value?.id || projects.value[0]?.id || null, episodeId: selectedEpisode.value?.id || null, title: '第 1 集剧本', content: '', language: 'zh-CN', status: 'Draft' }); scriptDialog.value = true }
function editScript(row) { Object.assign(scriptForm, row); scriptDialog.value = true }
async function saveScript() { try { const method = scriptForm.id ? 'PUT' : 'POST'; const path = scriptForm.id ? `/api/scripts/${scriptForm.id}` : '/api/scripts'; await api(path, { method, body: JSON.stringify(scriptForm) }); scriptDialog.value = false; await loadScripts(); ElMessage.success('剧本已保存') } catch (error) { ElMessage.error(error.message) } }
async function analyzeScript(row) { try { analysisResult.value = await api(`/api/scripts/${row.id}/analyze`, { method: 'POST', body: JSON.stringify({ scriptId: row.id, episodeId: row.episodeId, useLlm: true, replaceDraftShots: true }) }); await loadScripts(); if (selectedEpisode.value?.id === analysisResult.value.episodeId) await selectEpisode(selectedEpisode.value); ElMessage.success(`已拆分 ${analysisResult.value.shots.length} 个镜头（${analysisResult.value.provider}）`) } catch (error) { ElMessage.error(error.message) } }
async function startProduction() { if (!selectedEpisode.value) return ElMessage.warning('请先选择项目和剧集'); try { productionStatus.value = await api('/api/production/start', { method: 'POST', body: JSON.stringify({ episodeId: selectedEpisode.value.id, mode: 'ManualReview', candidateCount: 2 }) }); ElMessage.success('关键帧任务已按 GPU 串行队列提交') } catch (error) { ElMessage.error(error.message) } }
async function productionAction(action) { try { await api(`/api/production/${action}`, { method: 'POST' }); if (selectedEpisode.value) productionStatus.value = await api(`/api/production/status?episodeId=${selectedEpisode.value.id}`); ElMessage.success(action === 'pause' ? '生产队列已暂停' : '生产队列已继续') } catch (error) { ElMessage.error(error.message) } }
async function refreshProduction() { if (!selectedEpisode.value) return; try { productionStatus.value = await api(`/api/production/status?episodeId=${selectedEpisode.value.id}`); shots.value = await api(`/api/episodes/${selectedEpisode.value.id}/shots`) } catch (error) { ElMessage.error(error.message) } }
async function selectCandidate(shot) { try { const candidates = await api(`/api/shots/${shot.id}/candidates`); if (!candidates.length) return ElMessage.warning('该镜头还没有关键帧候选'); await api(`/api/shots/${shot.id}/candidates/${candidates[0].id}/select`, { method: 'POST' }); await api(`/api/shots/${shot.id}/approve-keyframe`, { method: 'POST' }); await refreshProduction(); ElMessage.success('已选择关键帧并提交 I2V') } catch (error) { ElMessage.error(error.message) } }
async function savePrompt(shot) { try { await api(`/api/shots/${shot.id}/prompt`, { method: 'PUT', body: JSON.stringify({ prompt: shot.prompt, negativePrompt: shot.negativePrompt, locked: shot.promptLocked, source: 'user' }) }); ElMessage.success('提示词已保存并记录版本') } catch (error) { ElMessage.error(error.message) } }
async function sendTts() { try { await api('/api/audio/tts', { method: 'POST', body: JSON.stringify(ttsForm) }); await loadTasks(); ElMessage.success('TTS 已加入 CPU 队列') } catch (error) { ElMessage.error(error.message) } }
async function uploadLibrary(event, bgm) { const file = event.target.files?.[0]; if (!file) return; const form = new FormData(); form.append('file', file); if (!bgm) form.append('category', 'environment'); try { await api(bgm ? '/api/bgm' : '/api/sound-effects', { method: 'POST', headers: {}, body: form }); ElMessage.success('音频素材已归档') } catch (error) { ElMessage.error(error.message) } finally { event.target.value = '' } }
async function renderEpisode() { if (!selectedEpisode.value) return; try { await api('/api/episode/render', { method: 'POST', body: JSON.stringify({ episodeId: selectedEpisode.value.id, includeSubtitles: true }) }); ElMessage.success('剧集合成已加入队列') } catch (error) { ElMessage.error(error.message) } }

async function taskAction(id, action) { try { await api(`/api/tasks/${id}/${action}`, { method: 'POST' }); await loadTasks(); ElMessage.success(action === 'cancel' ? '任务已取消' : '操作已提交') } catch (error) { ElMessage.error(error.message) } }
async function scanWorkflows() { try { const result = await api('/api/workflows/scan', { method: 'POST' }); await loadWorkflows(); ElMessage.success(`已扫描 ${result.scanned} 个工作流`) } catch (error) { ElMessage.error(error.message) } }
function mediaUrl(path) { return path ? `/api/media?path=${encodeURIComponent(path)}` : '' }
function isVideo(path) { return /\.(mp4|mov|webm|mkv)$/i.test(path || '') }
function statusType(status) { return ({ Succeeded: 'success', Running: 'warning', Pending: 'info', Failed: 'danger', Cancelled: 'info', Active: 'success', Approved: 'success', Passed: 'success', NeedReview: 'warning', Rejected: 'danger', Checking: 'warning', AutoChecking: 'warning', NotChecked: 'info' })[status] || 'info' }
const statusLabels = {
  Succeeded: '已完成', Running: '执行中', Pending: '排队中', Failed: '失败', Cancelled: '已取消',
  Active: '制作中', Paused: '已暂停', Archived: '已归档', Draft: '草稿', Ready: '待生成',
  ImageGenerating: '图片生成中', ImageReview: '关键帧待审核', VideoGenerating: '视频生成中', VideoReview: '视频待审核',
  AudioGenerating: '音频生成中', AudioReview: '音频待审核', Queued: '排队中', Retrying: '重试中', Publishing: '发布中', Published: '已发布',
  Completed: '已完成', Approved: '已通过', Passed: '已通过', NeedReview: '待人工复核',
  Rejected: '未通过', Checking: '检查中', AutoChecking: '自动检查中', NotChecked: '未验收'
}
const taskTypeLabels = {
  Image: '图片生成', ImageToVideo: '图生视频', Enhance: '视频增强', EpisodeRender: '剧集合成',
  QAExport: '验收导出', EpisodeQA: 'Episode 验收', ShotQA: '镜头验收', TTS: '语音生成',
  Audio: '音频处理', Subtitle: '字幕生成', Concat: '视频合并'
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
const modelTypeLabels = { checkpoint: '主模型', lora: 'LoRA', vae: 'VAE', controlnet: 'ControlNet', diffusion: '扩散模型', video: '视频模型' }
const providerLabels = { LocalRules: '本地规则解析', OpenAICompatible: '兼容 API', OpenAI: 'OpenAI' }
function statusLabel(status) { return statusLabels[status] || status || '未设置' }
function taskTypeLabel(taskType) { return taskTypeLabels[taskType] || taskType || '未知任务' }
function presetLabel(preset) { return presetLabels[preset] || preset || '标准验收' }
function issueTypeLabel(issueType) { return issueTypeLabels[issueType] || issueType || '其他问题' }
function severityLabel(severity) { return severityLabels[severity] || severity || '提示' }
function assetTypeLabel(assetType) { return assetTypeLabels[String(assetType || '').toLowerCase()] || assetType || '其他素材' }
function workflowTypeLabel(workflowType) { return workflowTypeLabels[String(workflowType || '').toLowerCase()] || workflowType || '其他工作流' }
function modelTypeLabel(modelType) { return modelTypeLabels[String(modelType || '').toLowerCase()] || modelType || '其他模型' }
function providerLabel(provider) { return providerLabels[provider] || provider || '本地解析' }
function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-' }
function formatBytes(value) { if (!value) return '-'; const units = ['B', 'KB', 'MB', 'GB']; let n = Number(value); let i = 0; while (n > 1024 && i < units.length - 1) { n /= 1024; i++ } return `${n.toFixed(i ? 1 : 0)} ${units[i]}` }
</script>

<template>
  <div class="studio-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">AI</div><div><div class="brand-title">视频工作室</div><div class="brand-subtitle">本地 AI 视频生产系统</div></div></div>
      <div class="side-section">制作中枢</div>
      <button v-for="item in navItems" :key="item.id" class="nav-item" :class="{ active: active === item.id }" @click="active = item.id"><span class="nav-icon">{{ item.icon }}</span><span><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span></button>
      <div class="sidebar-footer"><div class="connection-dot" :class="{ online }"></div><div><strong>{{ online ? '本地链路正常' : '等待服务连接' }}</strong><small>127.0.0.1 · RTX 4070</small></div></div>
    </aside>

    <main class="main-stage">
      <header class="topbar"><div><div class="eyebrow">AI 视频 / 工作区</div><h1>{{ currentNav.label }}</h1><p>{{ currentNav.hint }}</p></div><div class="top-actions"><el-tag :type="health?.comfy?.online ? 'success' : 'danger'" effect="dark">ComfyUI {{ health?.comfy?.online ? '在线' : '离线' }}</el-tag><el-tag type="info" effect="dark">{{ gpuText }}</el-tag><el-button circle plain @click="loadActive" :loading="loading">↻</el-button></div></header>
      <div v-if="errorText" class="error-banner"><span>连接提示：{{ errorText }}</span><el-button link @click="errorText = ''">关闭</el-button></div>

      <section v-if="active === 'dashboard'" class="page-content">
        <div class="hero-panel"><div><div class="eyebrow">生产控制</div><h2>把灵感变成可连续生产的镜头。</h2><p>角色、场景、工作流、任务和输出都落到本地资产库，适配 RTX 4070 12GB 的串行 GPU 队列。</p><div class="hero-buttons"><el-button type="primary" @click="active = 'projects'">进入项目制作</el-button><el-button plain @click="active = 'tasks'">查看任务队列</el-button></div></div><div class="hero-orbit"><div class="orbit-ring ring-1"></div><div class="orbit-ring ring-2"></div><div class="orbit-core">{{ dashboard.counts.succeededTasks || 0 }}<small>完成任务</small></div></div></div>
        <div class="stat-grid"><div class="stat-card" v-for="stat in [{label:'项目',key:'projects',icon:'▣'},{label:'角色资产',key:'characters',icon:'◎'},{label:'场景资产',key:'scenes',icon:'◇'},{label:'素材',key:'assets',icon:'▤'}]" :key="stat.key"><span class="stat-icon">{{ stat.icon }}</span><div><small>{{ stat.label }}</small><strong>{{ dashboard.counts[stat.key] || 0 }}</strong></div></div></div>
        <div class="dashboard-grid"><div class="panel"><div class="panel-head"><div><div class="eyebrow">GPU 监控</div><h3>显存与服务</h3></div><el-tag :type="health?.database?.online ? 'success' : 'danger'">数据库 {{ health?.database?.online ? '在线' : '待配置' }}</el-tag></div><div class="telemetry"><div class="telemetry-number">{{ health?.comfy?.gpu?.freeMiB || 0 }}<small>MiB 空闲</small></div><div class="telemetry-line"><span>GPU</span><strong>{{ health?.comfy?.gpu?.name || '未检测到' }}</strong></div><div class="telemetry-line"><span>FFmpeg</span><strong>{{ health?.ffmpeg?.available ? '可用' : '未找到' }}</strong></div><div class="telemetry-line"><span>队列策略</span><strong>并发 1 · 自动重试</strong></div></div></div><div class="panel"><div class="panel-head"><div><div class="eyebrow">最近活动</div><h3>最近任务</h3></div><el-button link @click="active = 'tasks'">全部任务 →</el-button></div><el-table :data="dashboard.recentTasks" size="small" class="dark-table"><el-table-column label="类型" width="130"><template #default="scope">{{ taskTypeLabel(scope.row.taskType) }}</template></el-table-column><el-table-column prop="shotTitle" label="镜头" min-width="150"/><el-table-column label="状态" width="110"><template #default="scope"><el-tag size="small" :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column></el-table></div></div>
      </section>

      <section v-else-if="active === 'projects'" class="page-content">
        <div class="toolbar"><div><div class="eyebrow">项目 / 分集 / 镜头</div><h2>项目制作台</h2></div><el-button type="primary" @click="resetProject">＋ 新建项目</el-button></div>
        <div class="workspace-grid"><div class="panel project-list"><div class="panel-head"><h3>项目库</h3><span class="muted">{{ projects.length }} 个项目</span></div><div v-for="project in projects" :key="project.id" class="project-row" :class="{ selected: selectedProject?.id === project.id }" @click="selectProject(project)"><div class="project-color"></div><div class="project-main"><strong>{{ project.name }}</strong><small>{{ project.description || '未填写项目简介' }}</small><div class="row-meta"><span>{{ project.episodeCount || 0 }} 集</span><span>{{ project.shotCount || 0 }} 镜头</span><span>{{ project.assetCount || 0 }} 素材</span></div></div><div class="row-actions"><el-button circle text @click.stop="editProject(project)">✎</el-button><el-button circle text type="danger" @click.stop="deleteProject(project)">×</el-button></div></div><el-empty v-if="!projects.length" description="还没有项目，先创建一个制作项目" /></div><div class="panel project-detail"><template v-if="selectedProject"><div class="panel-head"><div><div class="eyebrow">当前项目</div><h3>{{ selectedProject.name }}</h3></div><el-button type="primary" plain @click="openEpisodeDialog">＋ 新建一集</el-button></div><div class="episode-tabs"><button v-for="episode in episodes" :key="episode.id" :class="{ active: selectedEpisode?.id === episode.id }" @click="selectEpisode(episode)">EP {{ String(episode.episodeNumber).padStart(2, '0') }}<small>{{ episode.name }}</small></button><span v-if="!episodes.length" class="muted">尚未创建集</span></div><div v-if="selectedEpisode" class="shot-board"><div class="shot-board-head"><div><strong>{{ selectedEpisode.name }}</strong><span class="muted"> · 目标 {{ selectedEpisode.targetSeconds }} 秒 · {{ selectedEpisode.outputWidth }}×{{ selectedEpisode.outputHeight }}</span></div><div><el-button size="small" @click="openShotDialog">＋ 添加镜头</el-button><el-button size="small" type="success" plain @click="concatEpisode">合并本集</el-button></div></div><div class="shot-grid"><article v-for="shot in shots" :key="shot.id" class="shot-card"><div class="shot-preview" :class="{ empty: !shot.resultPath }"><template v-if="shot.resultPath && isVideo(shot.resultPath)"><video :src="mediaUrl(shot.resultPath)" muted preload="metadata"></video></template><template v-else-if="shot.resultPath"><img :src="mediaUrl(shot.resultPath)" /></template><template v-else><span>{{ String(shot.shotNumber).padStart(2, '0') }}</span><small>等待生成</small></template><label>镜头 {{ String(shot.shotNumber).padStart(2, '0') }}</label></div><div class="shot-body"><strong>{{ shot.title }}</strong><p>{{ shot.cameraPreset || '镜头未设定' }} · {{ shot.motionPreset || '动作未设定' }}</p><el-tag size="small" :type="statusType(shot.status)">{{ statusLabel(shot.status) }}</el-tag><el-button class="shot-run" size="small" type="primary" @click="queueShot(shot)">{{ shot.inputImagePath ? '图生视频' : '生成图片' }}</el-button></div></article><div v-if="!shots.length" class="empty-board"><span>＋</span><p>添加第一个镜头，开始搭建连续叙事</p><el-button plain @click="openShotDialog">创建镜头</el-button></div></div></div><el-empty v-else description="先创建一集，再开始添加镜头" /></template><el-empty v-else description="选择左侧项目查看制作内容" /></div></div>
      </section>

      <section v-else-if="active === 'characters'" class="page-content"><div class="toolbar"><div><div class="eyebrow">角色资产库</div><h2>角色资产库</h2></div><el-button type="primary" @click="resetCharacter">＋ 新建角色</el-button></div><div class="asset-grid"><article v-for="character in characters" :key="character.id" class="library-card"><div class="library-cover portrait"><img v-if="character.referencePath" :src="mediaUrl(character.referencePath)" /><span v-else>◎</span><label>{{ character.referenceCount || 0 }} 参考图</label></div><div class="library-content"><div class="card-title"><h3>{{ character.name }}</h3><el-tag size="small" type="success">身份锚点</el-tag></div><p>{{ character.faceFeatures || '尚未填写脸部特征' }}</p><div class="asset-lines"><span>发型</span><strong>{{ character.hair || '-' }}</strong><span>服装</span><strong>{{ character.clothes || '-' }}</strong></div><div class="card-actions"><el-button size="small" @click="editCharacter(character)">编辑</el-button><el-button size="small" plain @click="chooseReference(character)">上传锚点</el-button><el-button size="small" type="danger" text @click="deleteCharacter(character)">删除</el-button></div></div></article><div v-if="!characters.length" class="empty-board"><span>◎</span><p>角色资产会在这里保存身份锚点、固定提示词和 LoRA 路径</p><el-button plain @click="resetCharacter">创建角色</el-button></div></div></section>

      <section v-else-if="active === 'scenes'" class="page-content"><div class="toolbar"><div><div class="eyebrow">场景资产库</div><h2>场景资产库</h2></div><el-button type="primary" @click="resetScene">＋ 新建场景</el-button></div><div class="asset-grid"><article v-for="scene in scenes" :key="scene.id" class="library-card"><div class="library-cover landscape"><img v-if="scene.referencePath" :src="mediaUrl(scene.referencePath)" /><span v-else>◇</span><label>{{ scene.referenceCount || 0 }} 参考图</label></div><div class="library-content"><div class="card-title"><h3>{{ scene.name }}</h3><el-tag size="small" type="info">场景主图</el-tag></div><p>{{ scene.description || scene.fixedPrompt || '尚未填写场景描述' }}</p><div class="asset-lines"><span>风格</span><strong>{{ scene.style || '-' }}</strong><span>锚点</span><strong>{{ scene.anchorPath ? '已设置' : '待上传' }}</strong></div><div class="card-actions"><el-button size="small" @click="editScene(scene)">编辑</el-button><el-button size="small" plain @click="chooseSceneReference(scene)">上传主图</el-button><el-button size="small" type="danger" text @click="deleteScene(scene)">删除</el-button></div></div></article><div v-if="!scenes.length" class="empty-board"><span>◇</span><p>把建筑、房间、车辆和自然环境保存成可复用场景</p><el-button plain @click="resetScene">创建场景</el-button></div></div></section>

      <section v-else-if="active === 'scripts'" class="page-content"><div class="toolbar"><div><div class="eyebrow">剧本 / 解析 / 镜头</div><h2>剧本拆分台</h2></div><el-button type="primary" @click="resetScript">＋ 新建剧本</el-button></div><div class="two-col"><div class="panel"><div class="panel-head"><div><h3>剧本版本库</h3><span class="muted">支持 TXT / Markdown 内容粘贴与版本历史</span></div></div><div v-for="script in scripts" :key="script.id" class="script-row" :class="{ selected: selectedScript?.id === script.id }" @click="selectedScript = script"><div><strong>{{ script.title }}</strong><small>{{ script.episodeName || '未绑定集' }} · v{{ script.version }} · {{ statusLabel(script.status) }}</small></div><div class="row-actions"><el-button size="small" text @click.stop="editScript(script)">编辑</el-button><el-button size="small" type="primary" plain @click.stop="analyzeScript(script)">AI 拆分</el-button></div></div><el-empty v-if="!scripts.length" description="先创建一个剧本"/></div><div class="panel"><div class="panel-head"><div><h3>拆分结果</h3><span class="muted">自动识别人物、场景、动作、对白与镜头运动</span></div></div><template v-if="analysisResult"><div class="analysis-banner"><strong>{{ providerLabel(analysisResult.provider) }} 已完成解析</strong><span>{{ analysisResult.shots.length }} 个镜头 · 人物缺失 {{ analysisResult.missingCharacters.length }} · 场景缺失 {{ analysisResult.missingScenes.length }}</span></div><el-alert v-if="analysisResult.missingCharacters.length || analysisResult.missingScenes.length" title="发现待确认资产草稿，不会自动写入正式资产库" type="warning" :closable="false"/><el-table :data="analysisResult.shots" size="small" class="dark-table"><el-table-column prop="shotNumber" label="#" width="60"/><el-table-column prop="title" label="镜头" min-width="150"/><el-table-column prop="action" label="动作" min-width="180"/><el-table-column prop="cameraType" label="景别" width="110"/><el-table-column prop="cameraMotion" label="运动" width="120"/><el-table-column prop="durationSeconds" label="秒" width="65"/></el-table></template><el-empty v-else description="点击剧本右侧的 AI 拆分，生成可审核分镜"/></div></div></section>

      <section v-else-if="active === 'production'" class="page-content"><div class="toolbar"><div><div class="eyebrow">生产中心 / 人工复核</div><h2>剧集生产中心</h2></div><div><el-button plain @click="refreshProduction">刷新状态</el-button><el-button type="primary" @click="startProduction">开始关键帧生产</el-button><el-button type="warning" plain @click="productionAction('pause')">暂停队列</el-button><el-button type="success" plain @click="productionAction('resume')">继续队列</el-button></div></div><div class="panel" v-if="selectedEpisode"><div class="queue-banner"><div><strong>{{ selectedEpisode.name }}</strong><span>默认人工复核 · 关键帧候选数 2 · RTX 4070 GPU 并发 1</span></div><el-button size="small" type="success" plain @click="renderEpisode">合成剧集</el-button></div><div class="production-progress"><el-progress :percentage="productionStatus?.run ? Math.round((productionStatus.run.completedShots || 0) / Math.max(1, productionStatus.run.totalShots || shots.length) * 100) : 0" status="success"/><span>{{ productionStatus?.run?.completedShots || 0 }} / {{ productionStatus?.run?.totalShots || shots.length }} 完成</span></div><el-table :data="shots" class="dark-table" stripe><el-table-column prop="shotNumber" label="#" width="60"/><el-table-column prop="title" label="镜头" min-width="180"/><el-table-column prop="cameraType" label="景别" width="110"/><el-table-column prop="durationSeconds" label="时长" width="80"/><el-table-column label="状态" width="130"><template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column><el-table-column label="质量" width="80"><template #default="scope">{{ scope.row.qualityScore ? Number(scope.row.qualityScore).toFixed(0) : '-' }}</template></el-table-column><el-table-column label="提示词" min-width="280"><template #default="scope"><el-input v-model="scope.row.prompt" size="small" @change="savePrompt(scope.row)"/><small class="table-sub">v{{ scope.row.promptVersion || 1 }} · {{ scope.row.promptLocked ? '已锁定' : '可覆盖' }}</small></template></el-table-column><el-table-column label="审核" width="190" fixed="right"><template #default="scope"><el-button size="small" plain @click="selectCandidate(scope.row)" :disabled="!['ImageReview','Ready'].includes(scope.row.status)">选关键帧并生成视频</el-button></template></el-table-column></el-table></div><el-empty v-else description="请先在项目制作台选择项目和 Episode"/></section>

      <section v-else-if="active === 'qa'" class="page-content">
        <div class="toolbar"><div><div class="eyebrow">视频质量验收 / 发布门禁</div><h2>质量验收中心</h2></div><div class="qa-toolbar"><el-select v-model="qaPreset" size="small" style="width:150px"><el-option label="快速预检" value="Draft"/><el-option label="标准验收" value="Standard"/><el-option label="高质量发布" value="HighQuality"/></el-select><el-button plain @click="loadQa">刷新验收</el-button></div></div>
        <div class="qa-note panel"><div><strong>三层验收</strong><span>技术硬标准 → 镜头内容/稳定性 → 剧集连续性与发布锁定</span></div><small>没有大型视觉模型时，人物身份、动作语义、构图和跨镜头连续性会明确进入人工复核，不自动放行。</small></div>
        <div class="qa-layout"><div class="panel qa-episode-list"><div class="panel-head"><h3>剧集列表</h3><span class="muted">{{ qaEpisodes.length }} 集</span></div><button v-for="episode in qaEpisodes" :key="episode.id" class="qa-episode-row" :class="{ selected: qaSelectedEpisode?.id === episode.id }" @click="qaSelectedEpisode = episode; loadQaDetail()"><div><strong>{{ episode.name }}</strong><small>EP {{ String(episode.episodeNumber).padStart(3, '0') }} · {{ episode.shotCount || 0 }} 镜头</small></div><div class="qa-episode-score"><el-tag size="small" :type="statusType(episode.qaStatus)">{{ statusLabel(episode.qaStatus) }}</el-tag><strong>{{ episode.overallScore ? Number(episode.overallScore).toFixed(0) : '-' }}</strong></div></button><el-empty v-if="!qaEpisodes.length" description="还没有可验收的剧集"/></div>
          <div class="panel qa-detail"><template v-if="qaDetail"><div class="panel-head"><div><div class="eyebrow">剧集验收详情</div><h3>{{ qaDetail.episode.name }}</h3><span class="muted">技术标准：{{ presetLabel(qaPreset) }} · 目标 {{ qaDetail.episode.outputWidth }}×{{ qaDetail.episode.outputHeight }} / {{ qaDetail.episode.outputFps }} FPS</span></div><div class="qa-head-actions"><el-tag :type="statusType(qaDetail.episode.qaStatus)">{{ statusLabel(qaDetail.episode.qaStatus) }}</el-tag><el-tag v-if="qaDetail.episode.qaLocked" type="success">已锁定</el-tag><strong class="qa-big-score">{{ qaDetail.episode.overallScore ? Number(qaDetail.episode.overallScore).toFixed(0) : '-' }}</strong></div></div><div class="qa-actions"><el-button type="primary" @click="checkEpisodeQa">自动验收 Episode</el-button><el-button type="success" plain @click="reviewEpisodeQa('Approved')" :disabled="qaDetail.episode.qaLocked">通过并锁定</el-button><el-button plain @click="reviewEpisodeQa('NeedReview')">标记为人工复核</el-button><el-button plain @click="unlockQaEpisode" :disabled="!qaDetail.episode.qaLocked">解锁</el-button><el-button type="warning" plain @click="exportQaEpisode" :disabled="!qaDetail.episode.qaLocked">导出主片</el-button></div><el-table :data="qaDetail.shots" class="dark-table qa-table" stripe><el-table-column label="#" width="55"><template #default="scope">{{ scope.row.shot.shotNumber }}</template></el-table-column><el-table-column label="镜头" min-width="180"><template #default="scope"><strong>{{ scope.row.shot.title }}</strong><small class="table-sub">{{ scope.row.shot.sceneName || '未绑定场景' }}</small></template></el-table-column><el-table-column label="QA 状态" width="120"><template #default="scope"><el-tag size="small" :type="statusType(scope.row.shot.qaStatus)">{{ statusLabel(scope.row.shot.qaStatus) }}</el-tag></template></el-table-column><el-table-column label="得分" width="75"><template #default="scope">{{ scope.row.shot.qaScore ? Number(scope.row.shot.qaScore).toFixed(0) : '-' }}</template></el-table-column><el-table-column label="问题" width="75"><template #default="scope">{{ scope.row.issues?.length || 0 }}</template></el-table-column><el-table-column label="审核操作" min-width="330" fixed="right"><template #default="scope"><el-button size="small" type="primary" plain @click="checkShotQa(scope.row.shot)">验收</el-button><el-button size="small" type="success" plain @click="reviewShotQa(scope.row.shot, 'Passed')">通过</el-button><el-button size="small" type="danger" plain @click="reviewShotQa(scope.row.shot, 'Rejected')">拒绝</el-button><el-button size="small" type="warning" plain @click="regenerateQaShot(scope.row.shot)">重生成</el-button></template></el-table-column></el-table><div class="qa-issue-board"><div class="panel-head"><h3>剧集级问题</h3><span class="muted">{{ qaDetail.episodeIssues?.length || 0 }} 条</span></div><div v-for="issue in qaDetail.episodeIssues" :key="issue.id" class="qa-issue"><el-tag size="small" :type="issue.severity === 'Critical' || issue.severity === 'Error' ? 'danger' : 'warning'">{{ severityLabel(issue.severity) }}</el-tag><span>{{ issue.description }}</span><small>{{ issueTypeLabel(issue.issueType) }}</small></div><el-empty v-if="!qaDetail.episodeIssues?.length" description="暂无 剧集级问题" :image-size="50"/></div></template><el-empty v-else description="从左侧选择剧集查看验收详情"/></div></div>
      </section>

      <section v-else-if="active === 'voice'" class="page-content"><div class="toolbar"><div><div class="eyebrow">声音 / 本地 TTS</div><h2>声音工作台</h2></div><el-button plain @click="loadVoices">检测本地音色</el-button></div><div class="two-col"><div class="panel"><div class="panel-head"><h3>本地 TTS</h3><el-tag :type="voices.available ? 'success' : 'warning'">{{ voices.available ? 'Windows 系统语音可用' : 'TTS 不可用时不影响视频生产' }}</el-tag></div><el-form label-position="top"><el-form-item label="音色"><el-select v-model="ttsForm.voiceId" placeholder="系统中文默认音色"><el-option v-for="voice in voices.voices" :key="voice.id" :label="voice.name" :value="voice.id"/></el-select></el-form-item><el-form-item label="试听文本"><el-input v-model="ttsForm.text" type="textarea" :rows="5" placeholder="林雪：列车还在运行，我们还有机会。"/></el-form-item><div class="form-row"><el-form-item label="语速"><el-input-number v-model="ttsForm.speed" :min="0.5" :max="2" :step="0.1"/></el-form-item><el-form-item label="音高"><el-input-number v-model="ttsForm.pitch" :min="-10" :max="10"/></el-form-item></div><el-button type="primary" @click="sendTts">生成试听 / 加入队列</el-button></el-form></div><div class="panel"><div class="panel-head"><h3>使用规则</h3></div><p class="muted">相同文字、音色、语速和音高会复用 AudioCache，不重复生成。对白和旁白按 CPU 任务执行，不占用 RTX 4070 视频显存。</p><p class="muted">人物的 voice_id、剧集的旁白音色和音量配置通过后端保存；API Key 不会返回前端。</p></div></div></section>

      <section v-else-if="active === 'sfx'" class="page-content"><div class="toolbar"><div><div class="eyebrow">音效库</div><h2>音效与 BGM</h2></div><span class="muted">上传到 C:\install\AI\Data\SoundEffects / BGM</span></div><div class="two-col"><div class="panel"><div class="panel-head"><h3>音效库</h3></div><p class="muted">支持环境、机械、脚步、爆炸、雨声、风声、门、车辆、城市分类。当前阶段只管理用户上传的音频。</p><input type="file" accept="audio/*" @change="uploadLibrary($event, false)"/><el-button link @click="loadAssets">查看已入库素材</el-button></div><div class="panel"><div class="panel-head"><h3>BGM 库</h3></div><p class="muted">剧集可绑定多条 BGM，最终通过 FFmpeg 混音，默认降低 BGM 音量保证人声优先。</p><input type="file" accept="audio/*" @change="uploadLibrary($event, true)"/></div></div></section>

      <section v-else-if="active === 'tasks'" class="page-content"><div class="toolbar"><div><div class="eyebrow">生成队列 / 历史</div><h2>任务中心</h2></div><el-button plain @click="loadTasks">刷新队列</el-button></div><div class="panel"><div class="queue-banner"><div><strong>GPU 串行保护已启用</strong><span>RTX 4070 12GB · 大模型任务并发 1 · 失败自动重试最多 2 次</span></div><el-tag type="warning">{{ tasks.filter(x => x.status === 'Running').length }} Running</el-tag></div><el-table :data="tasks" class="dark-table" stripe><el-table-column prop="id" label="#" width="75"/><el-table-column label="任务" min-width="210"><template #default="scope"><strong>{{ taskTypeLabel(scope.row.taskType) }}</strong><small class="table-sub">{{ scope.row.projectName || '未关联项目' }} · {{ scope.row.shotTitle || '独立任务' }}</small></template></el-table-column><el-table-column label="状态" width="110"><template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column><el-table-column label="失败原因" width="150"><template #default="scope">{{ scope.row.errorType || '-' }}</template></el-table-column><el-table-column label="GPU 峰值" width="130"><template #default="scope">{{ scope.row.vramPeakMiB ? `${scope.row.vramPeakMiB} MiB` : '-' }}</template></el-table-column><el-table-column label="耗时" width="110"><template #default="scope">{{ scope.row.durationMs ? `${(scope.row.durationMs / 1000).toFixed(1)}s` : '-' }}</template></el-table-column><el-table-column label="创建时间" width="180"><template #default="scope">{{ formatDate(scope.row.createdAt) }}</template></el-table-column><el-table-column label="操作" width="220" fixed="right"><template #default="scope"><el-button v-if="['Pending','Running'].includes(scope.row.status)" size="small" type="danger" text @click="taskAction(scope.row.id, 'cancel')">取消</el-button><el-button v-if="scope.row.status === 'Failed'" size="small" type="warning" text @click="taskAction(scope.row.id, 'retry')">重试</el-button><el-button v-if="['Succeeded','Failed','Cancelled'].includes(scope.row.status)" size="small" text @click="taskAction(scope.row.id, 'rerun')">重跑</el-button></template></el-table-column></el-table><el-empty v-if="!tasks.length" description="暂无任务，去项目制作台生成第一个镜头" /></div></section>

      <section v-else-if="active === 'assets'" class="page-content"><div class="toolbar"><div><div class="eyebrow">本地素材库</div><h2>素材中心</h2></div><el-button plain @click="loadAssets">刷新素材</el-button></div><div class="asset-grid media-grid"><article v-for="asset in assets" :key="asset.id" class="media-card"><div class="media-preview"><video v-if="isVideo(asset.path)" :src="mediaUrl(asset.path)" controls preload="metadata"></video><img v-else :src="mediaUrl(asset.path)" /></div><div class="media-info"><strong>{{ asset.name }}</strong><span>{{ assetTypeLabel(asset.assetType) }} · {{ formatBytes(asset.sizeBytes) }}</span><small>{{ asset.width || '-' }}×{{ asset.height || '-' }} · {{ asset.durationSeconds ? `${Number(asset.durationSeconds).toFixed(2)}s` : '静态' }}</small></div></article><div v-if="!assets.length" class="empty-board"><span>▤</span><p>生成后的图片、视频与最终输出会自动登记到素材库</p></div></div></section>

      <section v-else-if="active === 'workflows'" class="page-content"><div class="toolbar"><div><div class="eyebrow">ComfyUI 目录</div><h2>工作流与模型</h2></div><el-button type="primary" plain @click="scanWorkflows">扫描现有目录</el-button></div><div class="two-col"><div class="panel"><div class="panel-head"><div><h3>工作流</h3><span class="muted">{{ workflows.length }} 个 JSON 工作流</span></div></div><el-table :data="workflows" class="dark-table" size="small"><el-table-column prop="name" label="名称" min-width="210"/><el-table-column prop="workflowType" label="类型" width="130"><template #default="scope"><el-tag size="small" type="info">{{ workflowTypeLabel(scope.row.workflowType) }}</el-tag></template></el-table-column><el-table-column prop="modelName" label="模型" min-width="180"/><el-table-column label="路径" min-width="250"><template #default="scope"><span class="path-text">{{ scope.row.path }}</span></template></el-table-column></el-table></div><div class="panel"><div class="panel-head"><div><h3>模型资产</h3><span class="muted">{{ models.length }} 个文件</span></div></div><el-table :data="models" class="dark-table" size="small"><el-table-column prop="name" label="文件" min-width="200"/><el-table-column label="类型" width="110"><template #default="scope">{{ modelTypeLabel(scope.row.modelType) }}</template></el-table-column><el-table-column label="大小" width="100"><template #default="scope">{{ formatBytes(scope.row.fileSizeBytes) }}</template></el-table-column></el-table></div></div></section>

      <section v-else-if="active === 'system'" class="page-content"><div class="toolbar"><div><div class="eyebrow">本地运行 / 诊断</div><h2>系统设置</h2></div><el-button plain @click="loadSystem">重新诊断</el-button></div><div class="system-grid"><div class="panel"><div class="panel-head"><h3>连接状态</h3></div><div class="check-list"><div><span>MySQL 8</span><el-tag :type="health?.database?.online ? 'success' : 'danger'">{{ health?.database?.online ? '在线' : '待配置凭据' }}</el-tag></div><div><span>ComfyUI API</span><el-tag :type="health?.comfy?.online ? 'success' : 'danger'">{{ health?.comfy?.online ? '在线' : '离线' }}</el-tag></div><div><span>FFmpeg / FFprobe</span><el-tag :type="health?.ffmpeg?.available ? 'success' : 'danger'">{{ health?.ffmpeg?.available ? '可用' : '缺失' }}</el-tag></div><div><span>监听地址</span><code>127.0.0.1:18080</code></div></div></div><div class="panel"><div class="panel-head"><h3>路径策略</h3></div><div class="path-list"><div><span>VideoStudio</span><code>{{ settings?.root || 'C:\\install\\AI\\VideoStudio' }}</code></div><div><span>数据</span><code>{{ settings?.data || 'C:\\install\\AI\\Data' }}</code></div><div><span>模型</span><code>{{ settings?.models || 'C:\\install\\AI\\Models' }}</code></div><div><span>工作流</span><code>{{ settings?.workflows || 'C:\\install\\AI\\Workflows' }}</code></div></div></div><div class="panel system-note"><div class="eyebrow">操作指南</div><h3>长期使用建议</h3><p>把角色身份锚点、场景主图和固定提示词先存入资产库，再从项目镜头提交任务。视频任务始终串行执行，避免 12GB 显存被多个大模型同时占用。</p><p>数据库密码只从 <code>config\local.env</code> 读取，不写入源码、前端或日志。</p></div></div></section>
    </main>

    <input id="reference-input" type="file" accept="image/*" hidden @change="onReferenceFile" />
    <el-dialog v-model="projectDialog" :title="projectForm.id ? '编辑项目' : '新建项目'" width="620px"><el-form label-position="top"><el-form-item label="项目名称"><el-input v-model="projectForm.name" placeholder="例如：末日科幻列车" /></el-form-item><el-form-item label="简介"><el-input v-model="projectForm.description" type="textarea" :rows="4" placeholder="项目主题、风格和制作目标" /></el-form-item><div class="form-row"><el-form-item label="画面比例"><el-select v-model="projectForm.aspectRatio"><el-option label="横屏 16:9" value="16:9"/><el-option label="竖屏 9:16" value="9:16"/><el-option label="方形 1:1" value="1:1"/></el-select></el-form-item><el-form-item label="默认 FPS"><el-input-number v-model="projectForm.defaultFps" :min="24" :max="60"/></el-form-item><el-form-item label="状态"><el-select v-model="projectForm.status"><el-option label="制作中" value="Active"/><el-option label="暂停" value="Paused"/><el-option label="归档" value="Archived"/></el-select></el-form-item></div><div class="form-row"><el-form-item label="默认宽"><el-input-number v-model="projectForm.defaultWidth" :min="256" :step="64"/></el-form-item><el-form-item label="默认高"><el-input-number v-model="projectForm.defaultHeight" :min="256" :step="64"/></el-form-item><el-form-item label="风格"><el-input v-model="projectForm.style" placeholder="电影感、写实风格"/></el-form-item></div><el-form-item label="提示词 风格"><el-input v-model="projectForm.promptStyle" placeholder="真实、动作克制、身份一致"/></el-form-item></el-form><template #footer><el-button @click="projectDialog = false">取消</el-button><el-button type="primary" @click="saveProject">保存项目</el-button></template></el-dialog>
    <el-dialog v-model="episodeDialog" title="新建一集" width="560px"><el-form label-position="top"><div class="form-row"><el-form-item label="集数"><el-input-number v-model="episodeForm.episodeNumber" :min="1"/></el-form-item><el-form-item label="目标时长（秒）"><el-input-number v-model="episodeForm.targetSeconds" :min="1"/></el-form-item><el-form-item label="输出帧率"><el-input-number v-model="episodeForm.outputFps" :min="24" :max="60"/></el-form-item></div><el-form-item label="集名称"><el-input v-model="episodeForm.name"/></el-form-item><el-form-item label="制作备注"><el-input v-model="episodeForm.description" type="textarea" :rows="3"/></el-form-item></el-form><template #footer><el-button @click="episodeDialog = false">取消</el-button><el-button type="primary" @click="saveEpisode">创建本集</el-button></template></el-dialog>
    <el-dialog v-model="shotDialog" title="添加镜头" width="720px"><el-form label-position="top"><div class="form-row"><el-form-item label="镜头号"><el-input-number v-model="shotForm.shotNumber" :min="1"/></el-form-item><el-form-item label="宽"><el-input-number v-model="shotForm.width" :min="256" :step="64"/></el-form-item><el-form-item label="高"><el-input-number v-model="shotForm.height" :min="256" :step="64"/></el-form-item><el-form-item label="帧数"><el-input-number v-model="shotForm.frames" :min="25" :max="241"/></el-form-item></div><el-form-item label="镜头标题"><el-input v-model="shotForm.title"/></el-form-item><el-form-item label="正向提示词"><el-input v-model="shotForm.prompt" type="textarea" :rows="3" placeholder="人物、动作、场景、光线和电影镜头语言"/></el-form-item><el-form-item label="输入参考图（图生视频）"><el-input v-model="shotForm.inputImagePath" placeholder="C:\\install\\AI\\Data\\Images\\keyframe.png"/></el-form-item><div class="form-row"><el-form-item label="镜头预设"><el-input v-model="shotForm.cameraPreset"/></el-form-item><el-form-item label="动作预设"><el-input v-model="shotForm.motionPreset"/></el-form-item><el-form-item label="随机种子"><el-input-number v-model="shotForm.seed" :min="0"/></el-form-item></div><el-form-item label="负面提示词"><el-input v-model="shotForm.negativePrompt" type="textarea" :rows="2"/></el-form-item></el-form><template #footer><el-button @click="shotDialog = false">取消</el-button><el-button type="primary" @click="saveShot">保存镜头</el-button></template></el-dialog>
    <el-dialog v-model="characterDialog" :title="characterForm.id ? '编辑角色资产' : '新建角色资产'" width="720px"><el-form label-position="top"><div class="form-row"><el-form-item label="角色名"><el-input v-model="characterForm.name"/></el-form-item><el-form-item label="年龄设定"><el-input v-model="characterForm.ageSetting"/></el-form-item><el-form-item label="身体比例"><el-input v-model="characterForm.bodyRatio"/></el-form-item></div><el-form-item label="脸部特征"><el-input v-model="characterForm.faceFeatures" type="textarea" :rows="2" placeholder="脸型、眼睛、鼻子、肤质等固定特征"/></el-form-item><el-form-item label="发型"><el-input v-model="characterForm.hair"/></el-form-item><el-form-item label="服装"><el-input v-model="characterForm.clothes"/></el-form-item><div class="form-row"><el-form-item label="默认音色 ID"><el-input v-model="characterForm.voiceId" placeholder="留空使用系统中文默认音色"/></el-form-item><el-form-item label="语速"><el-input-number v-model="characterForm.voiceSpeed" :min="0.5" :max="2" :step="0.1"/></el-form-item><el-form-item label="音高"><el-input-number v-model="characterForm.voicePitch" :min="-10" :max="10"/></el-form-item></div><el-form-item label="固定提示词"><el-input v-model="characterForm.fixedPrompt" type="textarea" :rows="3"/></el-form-item><el-form-item label="负面提示词"><el-input v-model="characterForm.negativePrompt" type="textarea" :rows="2"/></el-form-item></el-form><template #footer><el-button @click="characterDialog = false">取消</el-button><el-button type="primary" @click="saveCharacter">保存角色</el-button></template></el-dialog>
    <el-dialog v-model="sceneDialog" :title="sceneForm.id ? '编辑场景资产' : '新建场景资产'" width="680px"><el-form label-position="top"><el-form-item label="场景名"><el-input v-model="sceneForm.name"/></el-form-item><el-form-item label="场景说明"><el-input v-model="sceneForm.description" type="textarea" :rows="3"/></el-form-item><el-form-item label="固定提示词"><el-input v-model="sceneForm.fixedPrompt" type="textarea" :rows="3"/></el-form-item><el-form-item label="风格"><el-input v-model="sceneForm.style" placeholder="电影感、写实风格"/></el-form-item><el-form-item label="负面提示词"><el-input v-model="sceneForm.negativePrompt" type="textarea" :rows="2"/></el-form-item></el-form><template #footer><el-button @click="sceneDialog = false">取消</el-button><el-button type="primary" @click="saveScene">保存场景</el-button></template></el-dialog>
    <el-dialog v-model="scriptDialog" :title="scriptForm.id ? '编辑剧本并生成新版本' : '新建剧本'" width="820px"><el-form label-position="top"><div class="form-row"><el-form-item label="项目"><el-select v-model="scriptForm.projectId" placeholder="选择项目"><el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id"/></el-select></el-form-item><el-form-item label="Episode"><el-select v-model="scriptForm.episodeId" clearable placeholder="选择 Episode"><el-option v-for="episode in episodes" :key="episode.id" :label="episode.name" :value="episode.id"/></el-select></el-form-item></div><el-form-item label="剧本标题"><el-input v-model="scriptForm.title"/></el-form-item><el-form-item label="TXT / Markdown 剧本内容"><el-input v-model="scriptForm.content" type="textarea" :rows="16" placeholder="场景 1：末日列车驾驶室，夜晚，雨声。&#10;林雪：列车还在运行。&#10;陈默握紧扶手，转头看向窗外。&#10;&#10;场景 2：车厢，中景，陈默向林雪挥手。"/></el-form-item></el-form><template #footer><el-button @click="scriptDialog = false">取消</el-button><el-button type="primary" @click="saveScript">保存剧本</el-button></template></el-dialog>
  </div>
</template>
