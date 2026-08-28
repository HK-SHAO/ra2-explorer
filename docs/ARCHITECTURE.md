# RA2 Explorer v0.3 架构

## 运行模型

RA2 Explorer 是单机、只读源数据的本地 Web 应用：

```text
合法安装目录 / Mod 目录
          │ 只读扫描与按需读取
          ▼
格式层（MIX / SHP / PAL / VXL / HVA / TMP / CSF / INI / WAV / PCX）
          │
          ▼
SQLite 索引 ── 语义层（RULES / ART / CSF / 组件关联）── CLI
                    │
                 FastAPI
                    │ 回环地址
                    ▼
              React 浏览器界面
```

Python 服务是唯一的数据访问入口。CLI 和 HTTP API 都调用 `SourceLibrary`、`AssetReader` 与格式层，不维护第二套解析逻辑。前端生产构建由同一服务提供，因此运行时不需要 Node，也不加载外部 CDN。

## 数据边界

- 用户的源目录只读；扫描器不会改写、移动或解压其中的文件。
- `.runtime/index.sqlite3` 保存索引，`.runtime/reference` 保存可重新下载的文件名数据库；当前用户提供的 `.runtime/RA2MD` 也保持为 Git 忽略的只读输入。
- 索引记录松散相对路径，或 MIX 根文件与嵌套条目链。导出/预览时重新读取源字节，并检查记录中的 CRC 与大小。
- 第一版不复制完整游戏内容，也不建立内容寻址存储。
- `.runtime`、真实游戏目录、参考仓库、虚拟环境和前端构建产物均不进入 Git。

## 格式支持矩阵

| 格式 | v0.2 能力 | 说明 |
| --- | --- | --- |
| MIX / MMX / YRO | 解析、递归索引、按需读取 | 基础、扩展和 Blowfish 加密索引；同时检测 RA2/TS 与经典哈希 |
| PAL | 解析、网格预览 | 768 字节、256 色、6 位色值扩展到 8 位 |
| SHP (TS/RA2) | 元数据、逐帧 PNG | 支持压缩 0–3、裁剪帧、透明索引 0、可选调色板 |
| VXL | 体素列解码、部件元数据、等距 PNG | 使用 802 字节真实头部、内嵌或外部调色板，限制异常列与总体素数 |
| HVA | 帧/部件/3×4 变换矩阵解析与组合时间轴 | VXL 组合预览按部件名应用 HVA 帧变换，并支持 8 向世界坐标旋转 |
| TMP / TEM / SNO / URB / UBN / LUN / DES | 地块元数据、逐地块 PNG | 使用 TS/RA2 52 字节块头、菱形像素、深度层和可选 extra 层；歧义扩展先按内容区别 TMP 与 SHP |
| CSF | 标签、反码 UTF-16LE、Extra Value、全文检索 | 使用真实的 ` FSC` / ` LBL` / ` RTS` / `WRTS` 标识 |
| INI / MAP / MPR / TXT | 编码探测、结构统计、全文预览与检索 | 支持 UTF-8/UTF-16、GB18030 和 Windows-1252 回退 |
| WAV | 元数据、浏览器内播放、原始导出 | PCM 直接播放；实际游戏中的 IMA ADPCM 按请求转为 PCM16，原始导出不变；AUD/BAG 目前仍只索引导出 |
| PCX | 尺寸/色彩模式、PNG 预览 | 通过 Pillow 解码并限制最大预览像素数 |
| AUD / BAG / IDX / VPL / FNT / VQA / BIK | 索引、搜索、原始导出 | 已识别但尚未语义解码 |
| 未知条目 | CRC、大小、原始导出 | 文件名未知时显示稳定的 `crc_XXXXXXXX` 名称 |

## 单位语义目录

语义层按实际游戏覆盖顺序合并 `rules.ini` / `rulesmd.ini`、`art.ini` / `artmd.ini` 和 CSF。松散文件优先于 MIX，`expandmd##` / `expand##` 优先于基础归档，MD 配置叠加在原版配置之上。缓存键包含来源扫描时间、状态与资产数量，重新扫描后自动失效。

实体来自 `VehicleTypes`、`InfantryTypes`、`AircraftTypes` 和 `BuildingTypes`，经规则 `Image`、ART `Image` 与 `Voxel/NewTheater` 解析到真实文件。VXL 单位会关联主体、HVA、`TUR` 炮塔、`BARL` 炮管与 Cameo；SHP 单位会按剧场扩展选择主体。组合预览把每个 VXL 部件的边界、比例和 HVA 帧变换投影到同一个世界坐标系，不再把部件分别居中；同一接口可选择 HVA 帧、8 向朝向和阵营色。解析后的 VXL/HVA/SHP 对象保留一个有界的进程内 LRU，避免时间轴连续预览反复解码同一批组件，来源重扫后自动失效。

单位的 `Primary`、`Secondary`、`ElitePrimary` 与 `EliteSecondary` 会继续解析到武器节，再关联 `Projectile` 和 `Warhead` 节。详情接口保留每条关系的槽位、父节点、解析状态和关键参数；检索也覆盖这些依赖名称和参数。值 `none` 是游戏规则中的空引用，不计为缺失依赖。

调色板按资源语义选择：TMP 使用 `iso*.pal`，SHP/VXL 使用 `unit*.pal`；具体 TEM/SNO/URB/UBN/LUN/DES 变体优先从资产所在剧场归档判断。建筑 SHP 即使来自 `SNOW.MIX` 也使用 `unitsno.pal`，不能因其等距布局误用 `isosno.pal`。

语义目录当前是扫描索引上的可重建内存视图，不复制游戏内容，也不写回 RULES/ART。诊断接口分别统计实体可预览率、CSF 本地化率、组件关联率、单位类型覆盖和未解析依赖，并返回有限样本用于排障。完整 Mod Profile 和更多动画语义仍是后续能力。

Web UI 在现有三栏工作台中复用来源、搜索和详情交互：“游戏单位”默认显示载具，可切换步兵、航空器、建筑或全部实体；详情中的每个组件都能直接导出原始字节。

## MIX 名称与加密

RA2/TS 的文件名标识是对大写文件名执行带特殊尾部填充的 CRC32。早期 Westwood 游戏使用 rotate/add 算法；扫描器根据名称命中情况选择哈希类型，而不是假定所有 MIX 相同。

加密 MIX 先从 80 字节密钥源推导 Blowfish 密钥，再解密索引区。索引、条目范围、嵌套深度、条目数量和根归档大小均有上限与边界校验。损坏的单个归档会作为错误记录，灾难性扫描失败则保留上一版可用索引。

## 本地 API

主要契约：

- `GET /api/sources`、`POST /api/sources`：列出或导入源目录；
- `GET /api/discovery`：只读发现 Steam App 2229850、EA App/Origin 和旧版注册表安装；
- `POST /api/sources/{id}/scan`：原子替换该来源的索引；
- `GET /api/assets`：按来源、名称/路径/CRC 和格式分页检索；
- `GET /api/assets/{id}/content`：导出原始资产；
- `GET /api/assets/{id}/metadata`：按格式读取结构化元数据；
- `GET /api/assets/{id}/text`：预览/检索 CSF、INI、MAP 与 TXT；
- `GET /api/assets/{id}/shp`、`preview.png`：兼容 SHP 帧接口及统一图像预览；
- `GET /api/assets/{id}/media`：以正确媒体类型播放 WAV；
- `GET /api/entities`：按来源、名称、类型和可预览状态检索规则实体；
- `GET /api/entities/{source}/{entity}`：读取规则、ART 参数和实际组件来源；
- `GET /api/entities/{source}/{entity}/preview.png`：按 `frame`、`facing`、`player_color` 渲染 VXL 多部件或 SHP 单位预览；
- `GET /api/semantic/{source}/diagnostics`：检查实体、CSF、组件与武器依赖覆盖；
- `GET /api/player-colors`：列出预览可用的稳定阵营色预设；
- `GET /api/palettes`、`GET /api/stats`：辅助浏览；
- `POST /api/demo`：创建无商业素材的合成资料库；
- `POST /api/reference-data/names/sync`：同步固定提交的名称数据库。

OpenAPI 页面在 `/api/docs`。生产端口固定为 `46120`，可通过 `pythonw.exe` 无窗口运行并登记为当前用户登录自启。服务拒绝非本机 Host，CLI 也拒绝监听非回环地址。应用不会默认调用系统 URL 打开器，避免错误的浏览器/RemoteApp 关联产生外部弹窗。当前不包含认证，因此不得通过反向代理暴露到局域网或公网。

## 资源与可靠性限制

- 根 MIX 最大 1 GiB、单归档最多 4096 个条目、嵌套最大 6 层；这些是首版的防御性限制，不是格式极限。
- 搜索 API 单次最多返回 500 条，适合交互检索而非全库批量导出。
- 预览会把单个资产读入内存；尚无超大文件流式解码或后台任务队列。
- WAV 播放转码后的 PCM 上限为 512 MiB；不支持的 WAV 编码仍可原样导出。
- VXL 最多 512 个部件、400 万总体素，单部件预览最多 30 万体素；HVA 变换最多 100 万组。
- TMP 最多 16384 个槽，CSF 最多 10 万标签/20 万字符串，文本最多 16 MiB；限制用于抵抗损坏或恶意文件。
- 已在合成的基础/扩展/加密/嵌套 MIX、SHP 压缩和格式有效的 VXL/HVA/TMP/CSF/WAV 样本上验证。
- 用户提供的官方 RA2/YR 安装已完成全目录索引，并对 PAL、SHP、VXL、HVA、TMP、CSF、INI、MAP、TXT、WAV、PCX 做均匀抽样解析/渲染验证；当前 188 个真实资产全部通过。实测修正了零售空 SHP 帧、战区扩展歧义、TMP 未使用 extra 尺寸和 IMA ADPCM 播放等与合成样本不同的问题。
- 当前官方安装可建立 559 个规则实体，其中 526 个已有可预览主体（94.1%），909/951 个组件槽位已关联，1377 个武器链节点中仅 2 个引用未解析；`APOC` 已实测解析为“天启坦克”，并正确组合 `MTNK` 主体、炮塔、炮管及其 HVA 和 Cameo。`SHAD` 已实测读取 2 帧、3 部件 HVA，并通过不同帧、朝向与阵营色的组合预览。
- 真实游戏目录始终作为静态字节源处理；开发、验证与后台服务均不会调用其中的可执行文件。

## 参考实现与可重复数据

格式行为交叉核对了 OpenRA（开发快照 `2f09f50d5c2c3508c857f703e50af27af2d5625f`）、`iron-curtain-engine/cnc-formats` 和 `ra2web/ra2web-studio`。其中参考项目对 VXL 头部和 TMP 字段位置存在冲突，当前实现采用 OpenRA 已用于实际游戏内容的 802 字节 VXL 头与 TMP 读取顺序，而不是照搬较新的不一致描述。运行时名称库固定在 `cnc-formats` 提交 `77da596ed72a1201740e054855bf2ff60640bfa9`，下载清单会记录仓库、文件、提交、时间和条目数量。参考代码仓库仅用于开发核对，不参与应用运行。
