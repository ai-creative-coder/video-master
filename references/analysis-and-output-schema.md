# 分析与输出结构

## 内部证据数据

稳定标识：真实镜头 `SH001…`、剧情片段 `P001…`、人物 `CHAR001…`、道具 `PROP001…`、场景 `LOC001…`。时间至少保留 0.01 秒。

内部 manifest 保留媒体参数、自动候选、真实镜头、剧情片段、首尾状态、跨段连续性判断和 `agent_activation[]`。每项 Agent 记录 `role`、`status=STARTED|SKIPPED`、`reason` 与 `evidence_refs`；剪辑/VFX 或声音被跳过时必须满足对应门控契约。首尾状态仅用于分析与校验，不得把“入口、出口、承接上一段”等措辞复制到 Seedance 提示词。

事实标签使用 `OBSERVED`、`MEASURED`、`INFERRED`、`RECREATION_SPEC`、`UNKNOWN`、`USER_PROVIDED`。摄影设备、镜头型号、焦段和光圈通常是实现方案，必须标 `RECREATION_SPEC`，不能声称是原始拍摄器材。

## 01-完整故事剧本.md

按 `assets/screenplay-template.md` 输出。人物设定同时提供可用于生成的外貌、体态、服装、材质、表演习惯和关系描述。

## 02-图文分镜故事板

交付目录为 `02-图文分镜故事板/`，必须包含：

- `图文分镜故事板-完整制作版.html`
- `图文分镜故事板-总览图.png`
- `storyboard-images/clean/`
- `storyboard-images/annotated/`

PDF 可选。HTML 固定顺序：

1. 人物资产表。
2. 主要道具资产表。
3. 主要场景资产表。
4. 按剧情片段排列的逐镜图文故事板。
5. 常见失败修复提示词；没有专项修复项时明确标注无需额外修复提示词。

每项资产显示原视频代表帧、详细生成提示词、叙事功能和连续性锁定。每个真实镜头至少一张代表帧，并在对应图片下展示场景、可见实体、完整动作关系、人物表演链、动态首次登场、跨镜微事件链、摄影参数、光影、声音、分层文字/VFX、冲击事件和镜内剪辑。每个剧情片段末尾只展示该段的 `full_prompt`，不重复展示 `shot_prompt`。

不得另外交付逐镜分镜脚本、全局提示词 Markdown、逐段提示词 Markdown、修复提示词 Markdown 或 `prompt-data.json`。

## 内部 prompt-data schema

内部 `prompt-data.json` 是唯一真源，模式为 `4.0`。顶层至少包含：

- `source_duration`
- `global_consistency`
- `visual_master`
- `asset_library.characters[]`
- `asset_library.props[]`
- `asset_library.locations[]`
- `segments[]`

每项资产至少包含 `asset_id`、`name`、`frame_refs`、`description_prompt`、`narrative_function`、`continuity_lock`、`evidence_status`。`frame_refs` 引用已有的 `P001-node-01` 形式关键帧。

每个 `segments[]` 项至少包含：

- `segment_id`、`title`、`start`、`end`、`duration`、`shot_ids`、`keyframe_times`、`assets_used`
- `summary`、`segment_consistency`、`avoid`、`shot_prompts[]`、`timeline_events[]`、`timeline_continuity`、`full_prompt`

每个 `shot_prompts[]` 项必须与一个真实镜头一一对应，包含：

- `shot_id`、`start`、`end`、`duration`、`frame_refs`
- `present_entities`、`scene`、`action_beats[]`、`first_appearance_events[]`、`layer_events[]`、`impact_events[]`、`camera`、`lighting_color`、`sound`、`edit_instruction`、`shot_prompt`

顶层 `visual_master` 是全片视觉风格真源，必须包含 `core_style`、`visual_tone`、`color_system`、`tonal_structure`。这四项描述贯穿全片的稳定规则；逐镜 `lighting_color` 只描述相对母版的局部光影、天气、时间、色温、曝光或视觉锚点变化。局部字段不得重写一套全片风格，也不得与母版冲突。

每个 `action_beats[]` 项包含唯一 `beat_id`、主体资产 ID、主体类型、对象资产 ID、相对时间、动作、空间关系、动作节奏、物理反馈、证据等级和唯一 `timeline_fact`。人物或生物额外包含 `performance_chain`：情绪意图、可见表情、视线目标、预备、执行、延续和收势；其他主体禁止携带该字段。主体与对象资产必须存在于本镜 `present_entities`，从结构上阻止跨镜头污染。

跨主体或跨镜的微动作链在相关 `action_beats[]` 中使用同一 `interaction_chain_id=X001…`、`interaction_kind` 与非空 `interaction_object_ids[]`，并填写受控 `interaction_phase`、`state_in`、`state_out`。相邻阶段必须把前一条 `state_out` 原样复制为后一条 `state_in`，同一链不得更换交互类型或被追踪对象。`ownership_transfer` 至少四阶段，并分别覆盖触发/踢飞、接触/抓取、携带/返回、结果/观察者反应；不得只保留起点和结果镜头。

`first_appearance_events[]` 记录每位人物全片第一次可见时的出现类型、此前可见状态、具体来源空间、揭示触发、来源方向、画面位置、最先露出部位、初始姿态、揭示动作、第一动作、完整建立状态、观察者反应，以及至少两张属于该镜的 `evidence_frame_refs`。`layer_events[]` 将画内面屏、后期标题、环境 VFX、UI 叠层和转场 VFX 分开。`impact_events[]` 保存枪声、撞击、打击、爆炸等短促事件的源时码、音频线索、可见原因、目标、结果、因果结论及前/中/后加密关键帧。

每个 `timeline_events[]` 项输入片段内部相对时间 `start`、`end` 与 `source_refs[]`。构建器验证所有来源事实属于同一镜头、节点时间与每条来源事实存在正向重叠，再写入派生 `shot_id`，逐字取得 `timeline_fact`，并把该镜 `RECREATION_SPEC` 追加到只读 `text` 末尾。所有 `timeline_required=true` 的事实必须恰好被引用一次；引用不存在、遗漏、重复、跨镜误挂、只在边界相接而无重叠、摄影错配或构建后文字不等于“事实拼接+本镜摄影”均失败。这样时间轴是逐镜事实与摄影的唯一用户展示层，不再是第二套可自由改写的内容。

`camera` 必须包含 `equipment_name`、`lens_name`、`focal_length`、`aperture`、`camera_height_angle`、`composition`、`movement`、`focus_depth`，其数据性质为 `RECREATION_SPEC`。

每个剧情片段中的 `shot_prompts[]` 必须完整覆盖 `shot_ids`，所有关键帧必须映射到具体镜头。`full_prompt` 必须写明本段所需资产的具体特征，不能只引用资产编号。

`full_prompt` 固定按【生成任务】、【基础设定】、【氛围质感】、【时间轴】输出。【基础设定】包含人物角色、道具与车辆、场景环境、连续性要求和禁止项；【氛围质感】依次包含“全片视觉母版（核心风格、视觉基调、色彩体系、影调结构）”、本段光影与色彩、声音设计，不再单列摄影；【时间轴】直接渲染 `timeline_events[]`，每个节点末尾显示所属镜头摄影 `RECREATION_SPEC`，最后附一条 `timeline_continuity`。每个事实只进入一个主栏目，禁止把静态资产、光影或声音整段复制到时间轴；摄影参数只在对应时间节点出现。

构建 `full_prompt` 时，资产 `description_prompt` 进入对应基础设定；资产库 `continuity_lock` 不逐项注入，主 Agent 将本段必要不变量去重后写入 `segment_consistency`。`avoid` 不得反向复述 `segment_consistency`。动作节拍的 `spatial_relation` 描述主体与对象/环境的关系，不重复摄影机轨迹；`physical_feedback` 描述可见物理反馈，不重复 `sound`。

`shot_prompt` 是内部校验字段，用来确认逐镜动作和摄影信息完整；不得把它整段拼接进 `full_prompt`。故事板只把结构化、去重后的 `full_prompt` 作为可复制主提示词展示。

动作、首次登场、分层文字/VFX 与冲击事件是事实真源；`timeline_events[]` 是证据 ID 驱动的派生展示文本。修改事实必须回到对应逐镜源字段，禁止直接编辑已生成的时间轴文字。

负责提示词编译的 Agent 输出的 `NEEDS_INPUT` 仅是内部阻塞信号，不属于 schema 数据或交付内容。出现该信号时停止构建；补齐字段前不得创建或更新两项交付。最终内部 JSON、HTML 和剧本不得残留 `NEEDS_INPUT`。

## 文件编码

文本、JSON 和 HTML 使用 UTF-8。原视频帧保留原画幅和构图。
