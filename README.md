# RA2 Explorer

RA2 Explorer 是一个本地优先的《命令与征服：红色警戒 2》资产浏览器。它只读挂载用户自己的游戏目录，把 MIX 中的图像、体素、地形、文本和声音组织成可搜索、可预览、可播放、可导出的本地资产库。

当前可执行边界：

- 扫描本地目录中的松散资产和 MIX / MMX / YRO；
- 读取基础、扩展和 Blowfish 加密 MIX，并递归索引已知的嵌套 MIX；
- 同时解析 RA2/TS CRC32 与早期 Westwood 文件名哈希；
- 预览 PAL、RA2/TS SHP、TMP、PCX 和地图对象布局，并用 Three.js/WebGL 交互查看 VXL/HVA 三维组合与时间轴；
- 读取 CSF/INI/MAP 文本，解码 AUD 与 AUDIO.IDX/BAG，并把 Westwood/IMA ADPCM 转为浏览器可播放 WAV；
- 叠加 RULES/ART/SOUND/EVA/CSF 建立单位目录，关联常规及 `Weapon1…WeaponN` 武器、弹体、弹头、毁坏武器、碎片、动画、语音、音效和本地化台词；弹头 `AnimList` / `SplashList` 会按武器 `Damage` 选择实际候选，不再把整个列表误作连续动画；
- 合并官方中文 CSF 与可同步的 CnCNet 英文音频转录，正确读取 EVAMD 的 `Allied`/`Russian`/`Yuri` 映射，并按单位事件同时展示原文和中文文本；EVAMD 中的战役/合作任务对白与真正的 EVA 播报分开归类；
- 组合车辆主体、炮塔、炮管 VXL/HVA，按真实部件变换、TS/RA2 法线与 Westwood VPL 亮度表渲染，并用鼠标旋转、缩放和平移；
- 按需把 VQA/BIK 转为浏览器可播放 MP4，转换结果跨进程复用；
- 自动发现项目内 `.runtime\RA2MD`、Steam App 2229850、EA App/Origin 与兼容旧版安装；
- 对真实来源按格式均匀抽样，执行解析和首帧渲染验证；
- 通过 SQLite、HTTP API、CLI 和浏览器界面访问同一份索引；
- 在 list/grid 之间无损切换，按模型、地图、动画、语音、音效等用途浏览，并在设置中控制实际载入格式；
- 把索引、按需解包、解析元数据、PNG、WAV 与模型 JSON 持久化到 `.runtime\RA2MD-Ext`。

项目不会附带或自动上传商业游戏文件。当前官方 PC 版本是 Steam / EA App 中的 *Command & Conquer Red Alert 2 and Yuri's Revenge*；导入前需要由用户在相应平台合法安装。

## 立即运行

开发、构建、测试、检查、运行和 Git 命令全部强制使用 `cmd.exe`。以下命令均为 `cmd.exe` 语法，要求 Python 3.11+ 和 Node 18+：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .[dev]
.venv\Scripts\ra2exp.exe sync-names
.venv\Scripts\ra2exp.exe sync-audio-text
.venv\Scripts\ra2exp.exe import .runtime\RA2MD --name 本地游戏文件
cd frontend
npm ci
npm run build
cd ..
.venv\Scripts\ra2exp.exe background install
```

服务在 `http://127.0.0.1:46120` 无窗口后台运行，并登记为当前 Windows 用户的登录自启项。构建后的页面由 Python 服务从 `frontend\dist` 提供；运行时不需要 Node，也不会加载 CDN。`.runtime\RA2MD` 始终只读，应用不会启动其中的 EXE；所有派生结果进入独立的 `.runtime\RA2MD-Ext`。

页面左侧使用可收起为图标栏的统一树状导航：“单位”下直接选择载具、航空器、步兵和建筑，再依据 RULES 属性区分可建造、英雄、中立科技、平民/场景和任务对象。动画不再作为与单位重复的导航分类，而是在单位详情中依据 `Sequence`、HVA、`ArtType` 动画字段、`WeaponType.Anim`、`WarheadType.AnimList/SplashList`、`DeathWeapon` 和 Debris 字段浏览；没有来源字段的泛化事件不会由浏览器臆造。语音与音效按单位、EVA、战役、多人嘲讽、场景播报、战斗、环境和界面事件继续细分，不再设置“资源 / 单位”切换或重复的原始模型分类。页面没有顶部工具栏，左栏顶部是 RA2 Explorer，显示设置固定在左下角。游戏文本默认使用简体中文，可在显示设置中切换为繁体中文；单位默认角度同样在此设置并持久化，默认采用更容易识别主体的右前侧三分之四视角。两种字形都能检索同一条游戏文本。左栏折叠只更新导航尺寸，不会重建资产列表、详情或三维场景。声音分类来自 RULES/ART/SOUND/EVA/CSF、零售目录位置和稳定游戏命名的实际证据，而不是 WAV、AUD 或 BAG 容器类型；列表可按事件筛选、按单位和声音关系分组，同时显示可检索的台词、事件或任务说明，单击即可播放。地图、图像、地形、规则文本及其他底层格式可在显示设置中按需启用。

集合区按当前类型提供名称、说明、体积、造价、生命值等有效排序；造价与生命值均可升序或降序排列，缺失数值稳定置于末尾。list 使用双列高密度浏览，grid 用于视觉识别，两者共用查询、筛选、选中与增量分页状态。单位 grid 卡片只保留居中的缩略图和名称，SHP 图像被约束在固定预览框内并保留底部安全区；卡片右上角依据 `Owner`、`RequiredHouses` 和 `ForbiddenHouses` 显示紧凑的阵营或国家文本，无归属时不显示标记，也不使用名称后缀或内部 ID 区分。声音分组的主标题与 ID/附加信息使用单行省略布局；同一语音关联多个单位时直接以单位名作为标题，同名单位只在有官方阵营或国家归属时用括号消歧，不显示笼统的“共同使用”或内部 ID。只有具体单位关系才进入声音的“关联”页，纯事件关系改为紧凑的事件 ID/适用阵营标签。规则中的所有单位都会进入列表；`Image=null` 等规则占位对象不会误解析为 `NULL.SHP`，安装中确实没有主体文件的对象保留为准确的解析状态。页面会记住资料源、分类、筛选、选择、导航折叠、布局尺寸及列表/详情滚动位置。

详情根据类型切换为 VPL 光照三维模型、单位动作顺序播放或全帧网格、按非透明内容适配/缩放/平移的图像、紧凑音频、视频、地图布局或文本。SHP 与 VXL 分别把用户选择的相对视角映射到底层不同的朝向编号，避免步兵正面与载具正面互相翻转；VXL 仍可用鼠标自由旋转，“重置视角”回到显示设置中的默认角度。SHP 元数据保留每帧的真实非透明边界与成对阴影帧；缩略图以主体作为视觉锚点并为偏置阴影留足完整空间。自动适应保留稳定边距和放大上限，工具栏可在 25%–600% 间继续调整；切换单位时新帧先完成解码和内容测量，再替换仍保持原 fit 的上一帧。默认采用上方集合、下方宽屏详情；显示设置可切换为集合与窄屏详情左右排列，两种布局都可拖动分隔条调整详情大小，独立窗口始终采用宽屏详情。桌面宽屏的信息列使用独立可见滚动条并恢复上次位置，左侧预览和 canvas 保持固定；预览只填充详情的可用高度，不会被右侧长内容撑大或持续改变尺寸。切换单位时上一份有效详情会保留到新数据到达，避免请求间隙卸载 canvas 和 WebGL。空间不足而改成纵向单列时，详情自动退回一条整面板滚动链。

单位详情使用“声音 / 动画 / 数据” tabs；声音资产只有在存在具体单位关系时才使用“关联 / 数据” tabs，纯事件声音直接显示紧凑数据。唯一的播放/暂停控件固定在声音详情 header，切换任意信息 tab 时都保持挂载，点击不同声音卡片会自动播放，旧声音的迟到暂停事件不会取消新声音。声音详情会在切换卡片时保持用户上一次选择的 tab，并在刷新后恢复。单位声音按游戏规则中的选中、移动、开火等声音字段分组。动画子 tabs 使用 `HVA` / `Sequence`、`Buildup`、`ArtType`、`Weapon Anim`、`AnimList / SplashList`、`DeathWeapon / Debris` 等实际机制命名；每张卡显示来源规则节、字段、引用 ID 和选择依据。HVA 仅作为部件变换时间轴，不会被推断成移动或悬停事件。`AnimList` / `SplashList` 默认只呈现按 `Damage` 选出的候选，仍可在 canvas 固定位置切换检查完整候选表；`EMEffect` 与 Debris 的随机候选会明确标识。`Buildup` 替换主体预览，`ActiveAnim*`、生产和展开层与静态主体合成。`WeaponType.Anim` 的位置按对应 FireFLH、精英变体或 `WeaponXFLH` 投影；同一字段的八向素材合并为一张引用卡，并随三维相机跨越朝向区间切换，不重新载入模型。合成舞台与 WebGL 主体保持挂载，时间轴作为覆盖控件，不再因选择效果而重复加载模型或改变 canvas 尺寸。连续动画使用 SHP 的统一总画布和原始帧偏移进行序列级自适应，不再逐帧重新居中；VXL/HVA 同一模型换帧时保留初始取景和相机操作，下一帧完成加载和解码前持续显示上一有效帧。标签、规则属性和资源文件位于数据 tab 中并默认展开。

只开发 API 时可以不构建前端，接口文档位于 `http://127.0.0.1:46120/api/docs`。前端热更新使用 `cd frontend` 后运行 `npm run dev`。后台管理命令为：

```bat
.venv\Scripts\ra2exp.exe background status
.venv\Scripts\ra2exp.exe background stop
.venv\Scripts\ra2exp.exe background start
.venv\Scripts\ra2exp.exe background uninstall
```

安装项目后会生成正式 CLI `.venv\Scripts\ra2exp.exe`。现有 `.venv\Scripts\ra2-explorer.exe` 保留为兼容别名；激活虚拟环境后可以直接省略路径运行 `ra2exp`。交互式调试使用 `ra2exp serve`；它默认不会调用 Windows 外部程序。如确实需要自动打开浏览器，显式增加 `--open-browser`。

## 验证

```bat
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\ra2exp.exe verify <source-id> --samples-per-format 20
.venv\Scripts\ra2exp.exe entities <source-id> --query APOC
.venv\Scripts\ra2exp.exe entity <source-id> APOC
.venv\Scripts\ra2exp.exe entities <source-id> --missing
.venv\Scripts\ra2exp.exe semantic-check <source-id>
.venv\Scripts\ra2exp.exe sources
.venv\Scripts\ra2exp.exe stats <source-id>
.venv\Scripts\ra2exp.exe extract <source-id> --format vxl --limit 20
cd frontend
npm run build
```

真实 RA2 文件只用于本地 smoke test，不进入仓库。架构与数据边界见 [当前架构](docs/ARCHITECTURE.md)，合法游戏来源和本机导入见 [获取与导入游戏文件](docs/GAME_FILES.md)。

## 权利边界

RA2 Explorer 与 Electronic Arts 或其许可方无隶属或背书关系。游戏内容的提取、派生、上传和发布权限取决于用户所在地法律、平台条款以及具体素材权利；音乐、角色语音和第三方 Mod 资产应单独确认授权。
