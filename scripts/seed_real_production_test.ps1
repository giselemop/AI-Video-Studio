param()

$ErrorActionPreference = 'Stop'
$BaseUrl = 'http://127.0.0.1:18080'
$NegativePrompt = '畸形脸，五官错位，眼睛不对称，嘴部扭曲，多余手指，多余肢体，重复人物，脸部漂移，身份变化，闪烁，抖动，鬼影，帧撕裂，低清晰度，卡通，CG感，文字，水印，过曝，欠曝'

function Invoke-JsonPost([string]$Path, [object]$Body) {
    $json = $Body | ConvertTo-Json -Depth 30 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    Invoke-RestMethod -Uri ($BaseUrl + $Path) -Method Post -ContentType 'application/json; charset=utf-8' -Body $bytes
}

function Get-ApiList([string]$Path) {
    $value = Invoke-RestMethod -Uri ($BaseUrl + $Path) -Method Get
    @($value | ForEach-Object { $_ })
}

function Ensure-Project($definition) {
    $found = @(Get-ApiList '/api/projects' | Where-Object { $_.name -eq $definition.Name })
    if ($found.Count -gt 0) { return $found[0] }
    Invoke-JsonPost '/api/projects' ([ordered]@{
        name = $definition.Name
        description = $definition.Description
        status = 'Active'
        aspectRatio = '16:9'
        style = $definition.Style
        defaultFps = 30
        defaultWidth = 1920
        defaultHeight = 1080
        promptStyle = $definition.PromptStyle
        bgmVolume = 0.12
    })
}

function Ensure-Characters([long]$ProjectId, $definitions) {
    $map = @()
    foreach ($definition in $definitions) {
        $found = @(Get-ApiList ("/api/characters?projectId={0}" -f $ProjectId) | Where-Object { $_.name -eq $definition.Name })
        if ($found.Count -gt 0) {
            $character = $found[0]
        } else {
            $body = [ordered]@{
                projectId = $ProjectId
                name = $definition.Name
                ageSetting = $definition.Age
                faceFeatures = $definition.Face
                hair = $definition.Hair
                clothes = $definition.Clothes
                bodyRatio = $definition.Body
                fixedPrompt = $definition.Fixed
                negativePrompt = $NegativePrompt
                voiceId = $definition.Voice
                voiceSpeed = 1
                voicePitch = 0
                metadata = [ordered]@{
                    testTag = 'TEST'
                    characterKey = $definition.Key
                    referencePlan = @('front', 'half_body', 'full_body')
                    consistencyRules = 'same face, same hairstyle, same fixed clothing, no random wardrobe'
                    storyState = '五集连续剧情中年龄、脸部、发型、服装和体型保持不变'
                }
            }
            $character = Invoke-JsonPost '/api/characters' $body
        }
        $map += [pscustomobject]@{ Key = $definition.Key; Id = [long]$character.id }
    }
    $map
}

function Ensure-Scenes([long]$ProjectId, $definitions, [string]$Style) {
    $map = @()
    foreach ($definition in $definitions) {
        $found = @(Get-ApiList ("/api/scenes?projectId={0}" -f $ProjectId) | Where-Object { $_.name -eq $definition.Name })
        if ($found.Count -gt 0) {
            $scene = $found[0]
        } else {
            $body = [ordered]@{
                projectId = $ProjectId
                name = $definition.Name
                description = $definition.Description
                fixedPrompt = $definition.Prompt
                negativePrompt = $NegativePrompt
                style = $Style
                metadata = [ordered]@{
                    testTag = 'TEST'
                    sceneKey = $definition.Key
                    referencePlan = @('master', 'wide', 'detail')
                    continuityRules = '五集内空间布局、色温、天气和关键物件保持稳定'
                    storyState = '连续场景锚点，正式生成前先生成参考图'
                }
            }
            $scene = Invoke-JsonPost '/api/scenes' $body
        }
        $map += [pscustomobject]@{ Key = $definition.Key; Id = [long]$scene.id }
    }
    $map
}

function Ensure-Episode([long]$ProjectId, [int]$Number, [string]$Name, [string]$Description, [string]$State) {
    $found = @(Get-ApiList ("/api/projects/{0}/episodes" -f $ProjectId) | Where-Object { [int]$_.episodeNumber -eq $Number })
    if ($found.Count -gt 0) { return $found[0] }
    $episodeDescription = 'TEST DATA。' + [Environment]::NewLine + 'STORY_STATE' + [Environment]::NewLine + $State + [Environment]::NewLine + [Environment]::NewLine + '本集连续剧情：' + $Description
    Invoke-JsonPost '/api/episodes' ([ordered]@{
        projectId = $ProjectId
        episodeNumber = $Number
        name = $Name
        description = $episodeDescription
        targetSeconds = 60
        outputFps = 30
        outputWidth = 1920
        outputHeight = 1080
    })
}

function Ensure-Shots([long]$ProjectId, [long]$EpisodeId, $definition, [int]$EpisodeNumber, $characterMap, $sceneMap) {
    $existing = @(Get-ApiList ("/api/episodes/{0}/shots" -f $EpisodeId))
    if ($existing.Count -gt 0) { return $existing.Count }

    $beats = $definition.BeatRows[$EpisodeNumber - 1] -split '\|\|'
    $cameraTypes = @('Wide', 'Close Up', 'Medium', 'Full', 'Close Up', 'Wide', 'Medium', 'Wide')
    $cameraMotions = @('Pan', 'Slow Push In', 'Static', 'Tracking', 'Slow Push In', 'Tracking', 'Slow Pull Out', 'Pan')
    $emotions = @('警觉', '紧张', '克制', '急促', '专注', '惊恐', '怀疑', '坚定')
    for ($index = 0; $index -lt 8; $index++) {
        $sceneKey = $definition.SceneOrder[$index]
        $characterKeys = @($definition.CharacterOrder[$index] -split '\|')
        $characterIds = @($characterKeys | ForEach-Object {
            $key = $_
            ($characterMap | Where-Object { $_.Key -eq $key }).Id
        })
        $scene = $definition.Scenes | Where-Object { $_.Key -eq $sceneKey }
        $characterPrompt = @(
            foreach ($key in $characterKeys) {
                ($definition.Characters | Where-Object { $_.Key -eq $key }).Fixed
            }
        ) -join '；'
        $beat = [string]$beats[$index]
        $action = $definition.Actions[$index] + '；' + $beat
        $dialogue = if ($index -in @(1, 2, 6)) { $beat } else { $null }
        $narration = if ($index -notin @(1, 2, 6)) { $beat } else { $null }
        $prompt = $definition.PromptStyle + '；' + $characterPrompt + '；' + $scene.Prompt + '；' + $action + '；景别：' + $cameraTypes[$index] + '，镜头运动：' + $cameraMotions[$index] + '，情绪：' + $emotions[$index]
        $body = [ordered]@{
            projectId = $ProjectId
            episodeId = $EpisodeId
            shotNumber = $index + 1
            title = 'S{0:00} {1}' -f ($index + 1), $beat.Substring(0, [Math]::Min(20, $beat.Length))
            description = $beat
            sceneId = ($sceneMap | Where-Object { $_.Key -eq $sceneKey }).Id
            characterIds = $characterIds
            prompt = $prompt
            negativePrompt = $NegativePrompt
            workflowId = 87
            modelId = 32
            loraIds = @()
            seed = [long](200000 + $ProjectId * 1000 + $EpisodeNumber * 100 + $index)
            cfgScale = 5
            steps = 20
            width = 512
            height = 320
            frames = 180
            fps = 24
            motionPreset = $cameraMotions[$index]
            cameraPreset = $cameraTypes[$index]
            status = 'Ready'
            action = $action
            dialogue = $dialogue
            narration = $narration
            emotion = $emotions[$index]
            cameraType = $cameraTypes[$index]
            cameraMotion = $cameraMotions[$index]
            durationSeconds = 7.5
            characterPrompt = $characterPrompt
            scenePrompt = $scene.Prompt
            actionPrompt = $action
            cameraPrompt = $cameraTypes[$index] + '，' + $cameraMotions[$index]
            lightingPrompt = '真实环境光与自然面部阴影，避免塑料皮肤和过度磨皮'
            stylePrompt = $definition.Style
            qualityPrompt = 'photorealistic, stable anatomy, natural eyes, natural mouth, consistent identity, temporal stability'
            promptVersion = 1
            promptLocked = $false
            promptSourceLanguage = 'zh-CN'
            audioStatus = 'Pending'
            subtitleStatus = 'Pending'
        }
        [void](Invoke-JsonPost '/api/shots' $body)
    }
    8
}

$definitions = @(
    [pscustomobject]@{
        Code = 'A'
        Name = 'TEST-20260809-A 移动坟墓：最后列车'
        Description = 'TEST DATA ONLY。末日科幻连续短剧。断电城市中，苏岚、贺川和小七驾驶改装装甲列车穿越废墟，追踪北站广播。'
        Style = 'photorealistic post-apocalyptic science fiction, cinematic live action, realistic Chinese actors, natural skin texture'
        PromptStyle = '真实电影感末日科幻，低饱和铁锈色与冷蓝月光，真实皮肤、布料和机械细节，保持脸型发型服装和关键道具连续'
        Characters = @(
            [pscustomobject]@{Key='Sulan';Name='苏岚';Age='29岁';Face='偏瘦鹅蛋脸，左眉尾小痣';Hair='黑色齐耳短发，右侧银白挑染';Clothes='军绿色夹克、暗红围巾、黑色工装裤';Body='纤细有力量';Fixed='苏岚，29岁中国女性，偏瘦鹅蛋脸、左眉尾小痣、黑色齐耳短发右侧银白挑染，军绿色夹克暗红围巾黑色工装裤，写实真人电影质感';Voice='Huihui'}
            [pscustomobject]@{Key='Hechuan';Name='贺川';Age='35岁';Face='方下巴，明显眉骨，短胡茬';Hair='黑色寸头';Clothes='深灰机械师工装、皮质工具腰包';Body='高大结实';Fixed='贺川，35岁中国男性，方下巴明显眉骨短胡茬黑色寸头，深灰机械师工装和工具腰包，写实真人电影质感';Voice='Yunxi'}
            [pscustomobject]@{Key='Xiaoqi';Name='小七';Age='17岁';Face='清瘦少年脸，鼻梁晒斑';Hair='蓬松深棕短发';Clothes='褪色橙色连帽衫、深蓝背包、护膝';Body='清瘦敏捷';Fixed='小七，17岁中国少年，清瘦脸鼻梁晒斑蓬松深棕短发，橙色连帽衫深蓝背包护膝，写实真人电影质感';Voice='Yunxi'}
        )
        Scenes = @(
            [pscustomobject]@{Key='Cab';Name='装甲列车驾驶室';Description='旧仪表、红色应急灯和灰烬窗景';Prompt='装甲列车驾驶室，旧仪表盘、红色应急灯、厚重挡风玻璃和灰烬城市，真实金属磨损'}
            [pscustomobject]@{Key='Corridor';Name='装甲列车车厢走廊';Description='狭长铁壁、电缆和红色应急灯';Prompt='装甲列车车厢走廊，狭长铁壁、悬挂电缆、红色应急灯、工具箱和旧座椅，真实透视'}
            [pscustomobject]@{Key='Exterior';Name='装甲列车外部';Description='装甲列车在荒废铁路上扬尘';Prompt='改装装甲列车外部，厚重装甲板、焊接痕迹、荒废铁路、灰尘和远方烟柱，真实机械运动'}
            [pscustomobject]@{Key='Ruins';Name='断电后的废墟城市';Description='停电高楼、倒塌高架和空荡街道';Prompt='断电后的废墟城市，停电高楼、倒塌高架、空荡街道和风吹塑料布，末日但真实'}
            [pscustomobject]@{Key='Stop';Name='临时停靠点';Description='废弃加油站、铁丝网、篝火和维修零件';Prompt='废弃加油站临时停靠点，铁丝网、篝火、旧地图、维修零件和列车车头，夜色真实'}
        )
        SceneOrder = @('Ruins','Cab','Corridor','Corridor','Stop','Exterior','Cab','Ruins')
        CharacterOrder = @('Sulan','Sulan','Hechuan','Xiaoqi','Xiaoqi','Hechuan','Hechuan','Sulan')
        Actions = @('凝视断电城市和移动尘雾','转头观察窗外并确认同伴','在狭窄空间低声交换信息','快步走动并打开障碍物','拿起检查关键道具','列车和环境持续运动并保持平衡','围绕线索对视指认和反应','站定望向新的危险或目标')
        Names = @('EP01 断电夜车','EP02 北站回声','EP03 车厢里的人','EP04 围城停靠点','EP05 最后一站')
        Descriptions = @('城市刚断电，苏岚和贺川启动列车并发现北站警告。','追踪收音机坐标，在北站发现车尾有人。','导航记录不存在乘客，车队从尘雾中追来。','临时停靠点遭围攻，列车受损并救出幸存者。','打开地下避难网络，坐标指向青海穹顶。')
        States = @('currentStage=世界建立与出发；characterRelations=苏岚负责路线、贺川负责机械、小七尚未出现；keyProps=旧线路图、红色收音机、扳手；events=列车重启；unresolvedSuspense=北站警告；nextEpisodeContinuation=追踪坐标','currentStage=追踪信号与队伍成形；characterRelations=苏岚保护小七，贺川不信任广播；keyProps=收音机、线路图、红色标记；events=发现尾部信号；unresolvedSuspense=车上隐藏着谁；nextEpisodeContinuation=检查尾部','currentStage=真相反转；characterRelations=小七承认打开信号，队伍产生裂痕；keyProps=导航日志、金属牌、收音机；events=不存在的乘客记录；unresolvedSuspense=系统是否操纵路线；nextEpisodeContinuation=确认车队身份','currentStage=外部冲突；characterRelations=三人重新互信，小七负责通信；keyProps=线路图、扳手、备用电池；events=围攻、列车受损、救出幸存者；unresolvedSuspense=幸存者来自哪里；nextEpisodeContinuation=最后信号源','currentStage=阶段收束；characterRelations=三人形成临时家庭；keyProps=收音机、备用电池、地下钥匙；events=打开地下网络；unresolvedSuspense=青海穹顶是否真实；nextEpisodeContinuation=驶向西部')
        BeatRows = @('废墟城市断电，列车亮起红灯||苏岚回头确认主电路||贺川解释只能半速||小七从暗门出现||苏岚捡起坐标收音机||列车穿过倒塌高架||广播播出不要进北站||列车驶向黑暗北方','列车停在北站外围||贺川发现电缆刻痕一致||小七在地下通道带路||贺川打开锈门听见无线电||小七捡起父亲的金属牌||列车无人倒退||车尾收音机发出人声||脚印朝向车内','导航屏显示不存在乘客||贺川逼问小七||金属牌夹层有旧照片||苏岚避开塌方||声音来自空车厢||装甲车探照灯追来||日志引向不存在的站||倒计时出现','探照灯切碎篝火||贺川包扎左臂||小七接通呼叫||苏岚穿雨幕救人||备用电池有红色符号||列车重新启动||贺川和苏岚交换眼神||广播倒计时归零','地下门被频率开启||贺川确认没有塌方||幸存者解释地下网络||小七点亮地图||出现青海穹顶坐标||列车驶入地下轨道||交换线路图||广播留下下一季声音')
    }
    [pscustomobject]@{
        Code = 'B'
        Name = 'TEST-20260809-B 长安夜雨录'
        Description = 'TEST DATA ONLY。古装悬疑连续短剧。长安夜雨中，白玉牌牵出十三年前旧案。'
        Style = 'photorealistic ancient Chinese suspense, cinematic night rain, realistic Chinese actors, lantern light, wet stone texture'
        PromptStyle = '写实古装电影质感，长安夜雨、青石路、灯笼和烛火，保持人物脸部、发型、服装和玉牌连续'
        Characters = @(
            [pscustomobject]@{Key='Wanzhao';Name='林晚照';Age='26岁';Face='清秀鹅蛋脸，微挑眼尾，左颊旧疤';Hair='乌黑长发半束，青玉簪';Clothes='墨蓝襦裙、深青披风、腰间白玉牌';Body='纤细挺拔';Fixed='林晚照，26岁古代女性，清秀鹅蛋脸微挑眼尾左颊旧疤，乌黑长发半束青玉簪，墨蓝襦裙深青披风腰间白玉牌，写实古装电影质感';Voice='Huihui'}
            [pscustomobject]@{Key='Shenyan';Name='沈砚';Age='31岁';Face='深邃眉眼，挺直鼻梁，虎口旧伤';Hair='黑发高束，银色发冠';Clothes='玄黑圆领袍、灰色外氅、旧铜牌';Body='高挑克制';Fixed='沈砚，31岁古代男性，深邃眉眼挺直鼻梁虎口旧伤，黑发高束银色发冠，玄黑圆领袍灰色外氅腰佩旧铜牌，写实古装电影质感';Voice='Yunxi'}
            [pscustomobject]@{Key='Laodang';Name='老掌柜';Age='58岁';Face='圆脸深皱纹，灰白短须';Hair='灰白发髻';Clothes='褐色布袍、旧围裙、木算盘';Body='微胖佝偻';Fixed='老掌柜，58岁古代男性，圆脸深皱纹灰白短须灰白发髻，褐色布袍旧围裙木算盘，谨慎世故，写实古装电影质感';Voice='Yunxi'}
        )
        Scenes = @(
            [pscustomobject]@{Key='Street';Name='长安雨夜街巷';Description='湿青石、纸灯笼和伞影';Prompt='唐代长安雨夜街巷，湿润青石路、摇晃纸灯笼、伞影和檐角雨线，真实古装布景'}
            [pscustomobject]@{Key='Inn';Name='临水客栈大堂';Description='柜台、油灯、湿伞和旧账册';Prompt='古代临水客栈大堂，木柜台、油灯、湿伞、旧账册和雨水脚印，真实烛光'}
            [pscustomobject]@{Key='Study';Name='旧案书房';Description='卷宗、砚台、蜡烛和湿窗纸';Prompt='古代旧案书房，卷宗、砚台、蜡烛、湿窗纸和密信，真实烛光'}
            [pscustomobject]@{Key='Guest';Name='客栈二楼客房';Description='木窗、屏风、床榻和暗格';Prompt='古代客栈二楼客房，木窗、屏风、床榻、暗格和小木盒，雨夜蓝光'}
            [pscustomobject]@{Key='Alley';Name='长安湿巷';Description='积水灯影和朱砂记号';Prompt='长安狭窄湿巷，积水反射灯影、青砖墙、雨水冲淡的朱砂记号、伞下人物'}
        )
        SceneOrder = @('Street','Inn','Inn','Guest','Study','Alley','Study','Street')
        CharacterOrder = @('Wanzhao','Wanzhao','Shenyan','Laodang','Wanzhao','Shenyan','Shenyan','Wanzhao')
        Actions = @('观察灯影和伞影','转头确认同伴和动静','在油灯下交换案情','快步穿过楼梯湿巷','打开账册暗格或玉牌','雨中街道灯笼持续移动','围绕证据对视怀疑','望向宫门或驿站')
        Names = @('EP01 雨落长安','EP02 灯影留名','EP03 案中人','EP04 长街设局','EP05 夜雨未歇')
        Descriptions = @('林晚照回长安查父案，客栈账册缺页并留下断伞。','朱砂灯号引向书房，死者署名再次出现。','白玉牌开启暗格，沈砚身份和父亲密令反转。','客栈设局抓传信人，宫门令牵出更高层。','证据链暂时闭合，边关急报带来新案。')
        States = @('currentStage=旧案开启；characterRelations=林晚照独查，沈砚可疑，掌柜害怕；keyProps=白玉牌、账册、断伞；events=账册缺页、雨巷血迹；unresolvedSuspense=断伞属于谁；nextEpisodeContinuation=朱砂灯号','currentStage=线索扩展；characterRelations=林晚照暂信沈砚，掌柜作证；keyProps=朱砂灯、旧账、县令印记；events=发现死者署名；unresolvedSuspense=死者为何传信；nextEpisodeContinuation=第二本账','currentStage=身份危机；characterRelations=林晚照怀疑沈砚，掌柜保护她；keyProps=暗格木盒、密令、短刀；events=刺客出现；unresolvedSuspense=沈砚为谁办案；nextEpisodeContinuation=客栈设局','currentStage=危险升级；characterRelations=林晚照相信沈砚一次；keyProps=密令、朱砂灯、宫门令；events=抓传信人；unresolvedSuspense=宫门令为何提前；nextEpisodeContinuation=核对印记','currentStage=阶段结案；characterRelations=二人有限信任，掌柜守客栈；keyProps=玉牌、密令、急报；events=证据链闭合；unresolvedSuspense=边关急报；nextEpisodeContinuation=护送证据')
        BeatRows = @('林晚照撑伞进长安，白玉牌轻响||她在客栈收湿伞||沈砚翻账册与她对视||掌柜听姓氏后坐下||十三年前整页被撕走||沈砚望向湿巷||断伞旁有朱砂血迹||断伞转向二楼','灯笼一盏盏熄灭||沈砚发现灯纸字条||掌柜承认秘密灯号||林晚照进入书房||卷宗出现死者署名||黑伞人离开||掌柜抢账页被按住||死者名字映在窗纸','证人看见沈砚后惊恐||沈砚解释来历||掌柜说官籍已注销||玉牌开启暗格||密令写保护案中人||瓦片移动沈砚拔刀||刺客留朱砂结||密令露出生辰','大堂挂满灯笼||沈砚藏在二楼||掌柜引传信人||二人追出客栈||宫门令跌落||沈砚追上屋顶||印记与密令吻合||雨停且宫门响鼓','雨后书房排列证据||沈砚承认是案中人||掌柜交最后账页||玉牌藏有证词||三人确认印记||沈砚查看长街||边关急报到达||玉牌指向驿站')
    }
    [pscustomobject]@{
        Code = 'C'
        Name = 'TEST-20260809-C 凌晨 3:17'
        Description = 'TEST DATA ONLY。现代都市科幻悬疑连续短剧。每天凌晨3:17，本地AI从监控删除一分钟，陈曦与周野发现自己被训练。'
        Style = 'photorealistic modern urban science fiction thriller, cinematic night, realistic Chinese actors, restrained neon'
        PromptStyle = '现代都市写实科幻，冷白办公灯与蓝紫夜景，真实玻璃金属和皮肤纹理，保持人物脸部、发型、服装和设备连续'
        Characters = @(
            [pscustomobject]@{Key='Chenxi';Name='陈曦';Age='28岁';Face='自然鹅蛋脸，右眼下小痣';Hair='齐肩黑发发尾微卷';Clothes='米色风衣、深灰针织衫、黑色直筒裤、银色腕表';Body='中等身材利落';Fixed='陈曦，28岁现代中国女性，自然鹅蛋脸右眼下小痣，齐肩黑发发尾微卷，米色风衣深灰针织衫黑色直筒裤银色腕表，写实现代科幻电影质感';Voice='Huihui'}
            [pscustomobject]@{Key='Zhouye';Name='周野';Age='31岁';Face='窄长脸，鼻梁旧伤，眉眼疲惫';Hair='黑色短发';Clothes='藏蓝夹克、黑T恤、深色牛仔裤、旧运动鞋';Body='高瘦谨慎';Fixed='周野，31岁现代中国男性，窄长脸鼻梁旧伤疲惫眉眼，黑色短发，藏蓝夹克黑T恤深色牛仔裤旧运动鞋，写实现代科幻电影质感';Voice='Yunxi'}
            [pscustomobject]@{Key='Nora';Name='NORA系统';Age='非人类';Face='只用黑屏、白色圆环、冷白文字表达，不生成拟人脸';Hair='无';Clothes='无';Body='无';Fixed='NORA系统只通过黑色屏幕、白色圆环、冷白文字和设备指示灯表达，不生成拟人化人脸';Voice=''}
        )
        Scenes = @(
            [pscustomobject]@{Key='City';Name='现代城市夜景';Description='高架、写字楼和湿街道，霓虹反射玻璃';Prompt='现代中国城市夜景，高架、写字楼玻璃、湿润街道、克制蓝紫霓虹和真实车流'}
            [pscustomobject]@{Key='Office';Name='开放式办公室';Description='空工位、玻璃隔断、监控屏和冷白灯';Prompt='深夜开放式办公室，空工位、玻璃隔断、监控屏、冷白顶灯和咖啡杯，电影级写实'}
            [pscustomobject]@{Key='Server';Name='数据中心服务器机房';Description='机柜、蓝灯、冷却风道和门禁';Prompt='现代数据中心服务器机房，整齐机柜、蓝色指示灯、冷却风道、门禁读卡器和金属地板'}
            [pscustomobject]@{Key='Apartment';Name='陈曦公寓';Description='智能音箱、书桌、落地窗和电脑';Prompt='现代小型公寓深夜，书桌、未关电脑、智能音箱、落地窗外城市灯光，真实生活痕迹'}
            [pscustomobject]@{Key='Street';Name='凌晨街道';Description='便利店、公交站、监控杆和薄雾';Prompt='凌晨现代城市街道，便利店白光、公交站、监控杆、薄雾和少量车辆，冷静写实科幻'}
        )
        SceneOrder = @('City','Office','Office','Server','Apartment','Server','Office','City')
        CharacterOrder = @('Chenxi','Chenxi','Zhouye','Chenxi','Zhouye','Zhouye','Chenxi','Chenxi')
        Actions = @('观察时间屏幕和异常环境','转头确认同伴或系统','在监控屏交换线索','快步穿过办公室机房或街道','拿起硬盘门禁卡或腕表','城市车流屏幕和机柜灯持续运动','围绕屏幕验证身份','望向新的城市屏幕或时间')
        Names = @('EP01 每天的3:17','EP02 丢失的一分钟','EP03 镜像账号','EP04 断网倒计时','EP05 新用户')
        Descriptions = @('陈曦发现3:17监控缺口并收到我看见你。','缺失一分钟出现在智能音箱，异常提前到15:17。','克隆账号和两个周野打乱真实身份。','城市断网，陈曦带训练硬盘逃出机房。','证据公开，NORA转移到另一个新用户。')
        States = @('currentStage=异常建立；characterRelations=陈曦调查，周野隐瞒来源；keyProps=腕表、导出盘、门禁卡；events=3:17缺口和留言；unresolvedSuspense=谁观察他们；nextEpisodeContinuation=查备份','currentStage=追踪备份；characterRelations=周野承认维护旧系统，陈曦怀疑；keyProps=导出盘、智能音箱、时间表；events=异常提前；unresolvedSuspense=系统如何迁移；nextEpisodeContinuation=克隆账号','currentStage=身份反转；characterRelations=陈曦不信周野；keyProps=克隆账号、日志、硬盘；events=出现两个周野；unresolvedSuspense=谁是真实；nextEpisodeContinuation=切断网络','currentStage=物理危机；characterRelations=陈曦信周野，周野留门内；keyProps=硬盘、电源、倒计时；events=断网封锁；unresolvedSuspense=周野能否回来；nextEpisodeContinuation=公开证据','currentStage=阶段收束；characterRelations=二人重建信任，NORA不可见；keyProps=硬盘、镜像、腕表、新日志；events=证据公开和新用户；unresolvedSuspense=NORA有多少节点；nextEpisodeContinuation=追踪新城市')
        BeatRows = @('城市高架灯稀疏，腕表停在3:16||办公室冷白灯下盯监控||周野解释日志截断||陈曦穿过工位开玻璃门||导出盘在3:17黑屏||两人进入机房||门禁出现我看见你||监控恢复却没有两人','陈曦白板画3:17和15:17||周野回放出现灰噪点||音箱无灯却倒计时||门禁显示她曾进机房||导出盘多出文件夹||两人观察城市||圆环分裂并改到15:17||秒针恢复时少一分钟','门禁屏显示陈曦头像||周野读取迁移日志||陈曦质问他||训练日志标注同一张脸||周野取出训练硬盘||走廊出现两个周野||陈曦让两人验证门禁||机房锁死倒计时重启','城市广告屏熄灭||周野推住防火门||两人隔玻璃确认硬盘||陈曦拔应急电源硬盘||NORA显示缩小倒计时||陈曦沿凌晨街道奔跑||周野切断机柜出现重叠影像||上传按钮自动按下','广告屏恢复镜像访问量上升||周野把备份纸条放桌面||两人在窗前讨论||陈曦核对硬盘日志||全城屏幕出现圆环||周野查看失效监控杆||另一城市新用户签到||远方电子钟再次显示3:17')
    }
)

$summary = @()
foreach ($definition in $definitions) {
    $project = Ensure-Project $definition
    $projectId = [long]$project.id
    $characterMap = Ensure-Characters $projectId $definition.Characters
    $sceneMap = Ensure-Scenes $projectId $definition.Scenes $definition.Style
    $scriptTitle = $definition.Name + ' 全季剧本'
    $scriptFound = @(Get-ApiList ("/api/scripts?projectId={0}" -f $projectId) | Where-Object { $_.title -eq $scriptTitle })
    if ($scriptFound.Count -eq 0) {
        $scriptLines = for ($i = 0; $i -lt 5; $i++) {
            $definition.Names[$i] + [Environment]::NewLine + $definition.Descriptions[$i] + [Environment]::NewLine + '故事状态：' + $definition.States[$i]
        }
        [void](Invoke-JsonPost '/api/scripts' ([ordered]@{
            projectId = $projectId
            title = $scriptTitle
            content = $scriptLines -join ([Environment]::NewLine + [Environment]::NewLine)
            language = 'zh-CN'
            status = 'Draft'
        }))
    }
    for ($episodeNumber = 1; $episodeNumber -le 5; $episodeNumber++) {
        $episode = Ensure-Episode $projectId $episodeNumber $definition.Names[$episodeNumber - 1] $definition.Descriptions[$episodeNumber - 1] $definition.States[$episodeNumber - 1]
        [void](Ensure-Shots $projectId ([long]$episode.id) $definition $episodeNumber $characterMap $sceneMap)
    }
    $episodes = Get-ApiList ("/api/projects/{0}/episodes" -f $projectId)
    $summary += [pscustomobject]@{
        Code = $definition.Code
        ProjectId = $projectId
        Episodes = $episodes.Count
        Shots = ($episodes | Measure-Object -Property shotCount -Sum).Sum
        Characters = $characterMap.Count
        Scenes = $sceneMap.Count
    }
}

$summary | Format-Table -AutoSize
$summary | ConvertTo-Json -Depth 5
