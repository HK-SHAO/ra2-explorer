# RA2 Explorer v0.5 架构

## 运行模型

RA2 Explorer 是单机、只读源数据的本地 Web 应用：

```text
合法安装目录 / Mod 目录
          │ 只读扫描与按需读取
          ▼
格式层（MIX / SHP / VXL / HVA / TMP / MAP / CSF / INI / AUD / BAG / Video）
          │                         │
          ▼                         ▼
RA2MD-Ext 派生工作区 ←────── 按需解包 / PNG / WAV / MP4 / 场景 JSON
          │
SQLite 索引 ── 语义层（RULES / ART / CSF / 组件关联）── CLI
                    │
                 FastAPI
                    │ 回环地址
                    ▼
              React 浏览器界面
```

Python 服务是唯一的数据访问入口。CLI 和 HTTP API 都调用 `SourceLibrary`、`AssetReader` 与格式层，不维护第二套解析逻辑。前端生产构建由同一服务提供，因此运行时不需要 Node，也不加载外部 CDN。

## 数据边界

- `.runtime\RA2MD` 是只读官方安装；扫描、预览、验证和后台服务都不会修改文件或运行其中的 EXE。
- `.runtime\RA2MD-Ext\index\ra2-explorer.db` 保存索引；按需解包字节、解析元数据、PNG、WAV、MP4 和三维场景 JSON 位于 `RA2MD-Ext\artifacts\v1`。缓存键包含来源、扫描版本、资产标识、转换参数和解析器版本。
- `.runtime\reference` 保存可重新下载的文件名数据库。旧 `.runtime\ra2-explorer.db` 会一次性迁移到 `RA2MD-Ext`，新写入不再落到旧位置。
- 扫描器显式排除 `RA2MD-Ext`，防止派生结果被重复识别为原始游戏资产。
- 索引记录松散相对路径，或 MIX 根文件与嵌套条目链；首次读取时校验 CRC/大小并按需解出，后续同一扫描版本可以复用隔离缓存。
- `.runtime`、真实游戏目录、参考仓库、虚拟环境和前端构建产物均不进入 Git。

## 格式支持矩阵

| 格式 | 当前能力 | 说明 |
| --- | --- | --- |
| MIX / MMX / YRO | 解析、递归索引、按需读取 | 基础、扩展和 Blowfish 加密索引；同时检测 RA2/TS 与经典哈希 |
| PAL | 解析、网格预览 | 768 字节、256 色、6 位色值扩展到 8 位 |
| SHP (TS/RA2) | 元数据、逐帧 PNG | 支持压缩 0–3、裁剪帧、透明索引 0、可选调色板 |
| VXL | 体素列解码、等距 PNG、交互式 WebGL 三维模型 | 只发送表面体素并保留原始计数；Three.js 支持鼠标旋转、滚轮缩放、平移和阵营色 |
| HVA | 帧/部件/3×4 变换矩阵解析与组合时间轴 | VXL 组合预览按部件名应用 HVA 帧变换，并支持 8 向世界坐标旋转 |
| TMP / TEM / SNO / URB / UBN / LUN / DES | 地块元数据、逐地块 PNG | 使用 TS/RA2 52 字节块头、菱形像素、深度层和可选 extra 层；歧义扩展先按内容区别 TMP 与 SHP |
| CSF | 标签、反码 UTF-16LE、Extra Value、全文检索 | 使用真实的 ` FSC` / ` LBL` / ` RTS` / `WRTS` 标识 |
| INI / TXT | 编码探测、结构统计、全文预览与检索 | 支持 UTF-8/UTF-16、GB18030 和 Windows-1252 回退 |
| MAP / MPR | 文本、元数据、对象布局图 | 读取地图边界、环境、建筑、单位、步兵、航空器、地形对象和路径点；当前是结构示意图，不是完整等距地表复刻 |
| WAV | 元数据、浏览器内播放、原始导出 | PCM 直接播放；IMA ADPCM 按请求转为 PCM16 |
| AUD | 结构校验、Westwood/IMA ADPCM 解码、WAV 播放 | 支持压缩类型 1 与 99，容忍零售文件最后一块的声明差异 |
| AUDIO.IDX / BAG | IDX v2 展开、3,438 条虚拟语音、WAV 播放 | 通过偏移直接读取所需 BAG 片段，不缓存或载入整个 BAG；支持 PCM16 与 IMA ADPCM |
| PCX | 尺寸/色彩模式、PNG 预览 | 通过 Pillow 解码并限制最大预览像素数 |
| VQA / BIK | 索引、搜索、按需 MP4 播放、原始导出 | 调用系统 FFmpeg 转为 H.264/AAC；不执行游戏目录中的程序，转换结果持久化到 `RA2MD-Ext` |
| VPL / FNT | 索引、搜索、原始导出 | 可在素材设置中按需显示，尚未提供专用视图 |
| 未知条目 | CRC、大小、原始导出 | 文件名未知时显示稳定的 `crc_XXXXXXXX` 名称 |

## 单位语义目录

语义层按实际游戏覆盖顺序合并 `rules.ini` / `rulesmd.ini`、`art.ini` / `artmd.ini` 和 CSF。松散文件优先于 MIX，`expandmd##` / `expand##` 优先于基础归档，MD 配置叠加在原版配置之上。缓存键包含来源扫描时间、状态与资产数量，重新扫描后自动失效。

实体来自 `VehicleTypes`、`InfantryTypes`、`AircraftTypes` 和 `BuildingTypes`，经规则 `Image`、ART `Image` 与 `Voxel/NewTheater` 解析到真实文件。VXL 单位会关联主体、HVA、`TUR` 炮塔、`BARL` 炮管与 Cameo；SHP 单位会按剧场扩展选择主体。组合预览把每个 VXL 部件的边界、比例和 HVA 帧变换投影到同一个世界坐标系，不再把部件分别居中；同一接口可选择 HVA 帧、8 向朝向和阵营色。解析后的 VXL/HVA/SHP 对象保留一个有界的进程内 LRU，避免时间轴连续预览反复解码同一批组件，来源重扫后自动失效。

单位的 `Primary`、`Secondary`、`ElitePrimary` 与 `EliteSecondary` 会继续解析到武器节，再关联 `Projectile` 和 `Warhead` 节。详情接口保留每条关系的槽位、父节点、解析状态和关键参数；检索也覆盖这些依赖名称和参数。值 `none` 是游戏规则中的空引用，不计为缺失依赖。

声音关系从 RULES/ART 的语音、移动、部署、武器报告和动画字段继续追踪到 SOUNDMD/EVA、AUDIO.IDX/BAG、WAV/AUD 与 CSF。带 `VOX:` 本地化项的语音会同时返回台词文本；资产反向关联接口可以显示它属于哪个单位和事件。关系是从官方配置计算出的可重建视图，不写回源文件。

配色表（PAL）是 RA2 索引色资源的 256 色查找表：SHP/VXL 像素或体素保存的是颜色索引，而不是现代材质贴图。TMP 使用 `iso*.pal`，SHP/VXL 使用 `unit*.pal`；具体 TEM/SNO/URB/UBN/LUN/DES 变体优先从资产所在剧场归档判断。建筑 SHP 即使来自 `SNOW.MIX` 也使用 `unitsno.pal`，不能因其等距布局误用 `isosno.pal`。

语义目录当前是扫描索引上的可重建内存视图，不复制游戏内容，也不写回 RULES/ART。诊断接口分别统计实体可预览率、CSF 本地化率、组件关联率、单位类型覆盖和未解析依赖，并返回有限样本用于排障。完整 Mod Profile 和更多动画语义仍是后续能力。

Web UI 在三栏工作台中复用来源、搜索和详情交互。左栏是统一树：载具、航空器、步兵和建筑是“单位”的子节点，动画、语音、音效以及设置中启用的地图、图像、地形和规则文本是同级节点，不存在平行的“资源 / 单位”模式。中栏依据节点显示格式或语义标签，并提供服务端稳定排序；list/grid 共享查询、筛选、排序、选中和分页状态。不同格式分别进入三维、有效帧动画、图像、音频、视频、地图或文本视图。VXL 单体和组合单位使用 WebGL 真三维视图，光标可以旋转、缩放和平移。来源的 `scanned_at` 变化会同时刷新索引视图并切换派生缓存版本。

## MIX 名称与加密

RA2/TS 的文件名标识是对大写文件名执行带特殊尾部填充的 CRC32。早期 Westwood 游戏使用 rotate/add 算法；扫描器根据名称命中情况选择哈希类型，而不是假定所有 MIX 相同。

加密 MIX 先从 80 字节密钥源推导 Blowfish 密钥，再解密索引区。索引、条目范围、嵌套深度、条目数量和根归档大小均有上限与边界校验。损坏的单个归档会作为错误记录，灾难性扫描失败则保留上一版可用索引。

## 本地 API

主要契约：

- `GET /api/sources`、`POST /api/sources`、`DELETE /api/sources/{id}`：列出、导入或从索引移除源目录；删除接口不删除源文件；
- `GET /api/discovery`：只读发现 Steam App 2229850、EA App/Origin 和旧版注册表安装；
- `POST /api/sources/{id}/scan`：原子替换该来源的索引；
- `GET /api/assets`：按来源、名称/CRC 和一个或多个格式分页检索，并以名称或体积稳定排序；
- `GET /api/assets/{id}/content`：导出原始资产；
- `GET /api/assets/{id}/metadata`：按格式读取结构化元数据；
- `GET /api/assets/{id}/text`：预览/检索 CSF、INI、MAP 与 TXT；
- `GET /api/assets/{id}/shp`、`preview.png`：兼容 SHP 帧接口及统一图像预览；
- `GET /api/assets/{id}/media`：播放 WAV、AUD 或 AUDIO.BAG 虚拟语音；
- `GET /api/assets/{id}/video.mp4`：按需转换并播放 VQA/BIK；
- `GET /api/assets/{id}/associations`：读取声音、动画和单位的反向语义关系；
- `GET /api/assets/{id}/model.json`：读取 VXL 或同名 VXL/HVA 的浏览器三维场景，可选择 HVA 帧；
- `GET /api/entities`：按来源、名称、类型和可预览状态检索规则实体；
- `GET /api/entities/{source}/{entity}`：读取规则、ART 参数和实际组件来源；
- `GET /api/entities/{source}/{entity}/preview.png`：按 `frame`、`facing`、`player_color` 渲染 VXL 多部件或 SHP 单位预览；
- `GET /api/entities/{source}/{entity}/model.json`：读取组合 VXL/HVA 三维场景；
- `GET /api/semantic/{source}/diagnostics`：检查实体、CSF、组件与武器依赖覆盖；
- `GET /api/player-colors`：列出预览可用的稳定阵营色预设；
- `GET /api/palettes`、`GET /api/stats`：辅助浏览；
- `POST /api/reference-data/names/sync`：同步固定提交的名称数据库。

OpenAPI 页面在 `/api/docs`。生产端口固定为 `46120`，可通过 `pythonw.exe` 无窗口运行并登记为当前用户登录自启。服务拒绝非本机 Host，CLI 也拒绝监听非回环地址。应用不会默认调用系统 URL 打开器，避免错误的浏览器/RemoteApp 关联产生外部弹窗。当前不包含认证，因此不得通过反向代理暴露到局域网或公网。

## 资源与可靠性限制

- 根 MIX 最大 1 GiB、单归档最多 4096 个条目、嵌套最大 6 层；这些是首版的防御性限制，不是格式极限。
- 搜索 API 单次最多返回 500 条；前端通过可见滚动容器增量分页，不再把 500 条误表现为完整结果。
- MIX 松散条目通过 seek/read 读取，嵌套归档通过 mmap 视图遍历；BAG 虚拟音频只读取指定偏移片段。格式解码仍有单资产防御性上限，尚无持久任务队列。
- 视频首次播放需要 FFmpeg 转码，之后复用 `RA2MD-Ext` 中的 MP4；转换使用 `-nostdin`、无窗口子进程、超时和同键互斥，避免命令行挂起或重复工作。
- 音频播放转码后的 PCM 上限为 512 MiB；不支持的编码仍可原样导出。
- VXL 最多 512 个部件、400 万总体素，单部件预览最多 30 万体素；HVA 变换最多 100 万组。
- TMP 最多 16384 个槽，CSF 最多 10 万标签/20 万字符串，文本最多 16 MiB；限制用于抵抗损坏或恶意文件。
- 已在合成的基础/扩展/加密/嵌套 MIX、SHP 压缩和格式有效的 VXL/HVA/TMP/CSF/WAV 样本上验证。
- 用户提供的官方 RA2/YR 安装已完成全目录索引：16,820 个资产，其中 3,438 条来自 AUDIO.IDX/BAG 的实际语音。原有 11 类 188 个真实资产验证为 188/188；另对 23 个 AUD 全量通过，并对 BAG 语音抽样 100/100 通过。
- 当前官方安装可建立 559 个规则实体，其中 535 个已有可预览主体（95.7%）。剩余 24 个包括游戏规则中的 Dummy/占位对象以及官方归档未附带主体文件的对象；默认单位列表不会载入它们。`APOC` 已实测解析为“天启坦克”，并正确组合 `MTNK` 主体、炮塔、炮管及其 HVA、Cameo、语音和武器事件。`SHAD` 已实测读取 2 帧、3 部件 HVA，并通过不同帧、朝向与阵营色的组合预览。
- 真实游戏目录始终作为静态字节源处理；开发、验证与后台服务均不会调用其中的可执行文件。

## 参考实现与可重复数据

格式行为交叉核对了 OpenRA（开发快照 `2f09f50d5c2c3508c857f703e50af27af2d5625f`）、`iron-curtain-engine/cnc-formats` 和 `ra2web/ra2web-studio`。其中参考项目对 VXL 头部和 TMP 字段位置存在冲突，当前实现采用 OpenRA 已用于实际游戏内容的 802 字节 VXL 头与 TMP 读取顺序，而不是照搬较新的不一致描述。运行时名称库固定在 `cnc-formats` 提交 `77da596ed72a1201740e054855bf2ff60640bfa9`，下载清单会记录仓库、文件、提交、时间和条目数量。参考代码仓库仅用于开发核对，不参与应用运行。
