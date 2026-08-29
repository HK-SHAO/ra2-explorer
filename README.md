# RA2 Explorer

RA2 Explorer 是一个本地优先的《命令与征服：红色警戒 2》资产浏览器。它只读挂载用户自己的游戏目录，把 MIX 中的图像、体素、地形、文本和声音组织成可搜索、可预览、可播放、可导出的本地资产库。

当前可执行边界：

- 扫描本地目录中的松散资产和 MIX / MMX / YRO；
- 读取基础、扩展和 Blowfish 加密 MIX，并递归索引已知的嵌套 MIX；
- 同时解析 RA2/TS CRC32 与早期 Westwood 文件名哈希；
- 预览 PAL、RA2/TS SHP、TMP、PCX 和地图对象布局，并用 Three.js/WebGL 交互查看 VXL/HVA 三维组合与时间轴；
- 读取 CSF/INI/MAP 文本，解码 AUD 与 AUDIO.IDX/BAG，并把 Westwood/IMA ADPCM 转为浏览器可播放 WAV；
- 叠加 RULES/ART/SOUND/EVA/CSF 建立单位目录，关联武器、弹体、弹头、动画、语音、音效和本地化台词；
- 组合车辆主体、炮塔、炮管 VXL/HVA，按真实索引配色和阵营色显示，并用鼠标旋转、缩放和平移；
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
.venv\Scripts\ra2exp.exe import .runtime\RA2MD --name 本地游戏文件
cd frontend
npm ci
npm run build
cd ..
.venv\Scripts\ra2exp.exe background install
```

服务在 `http://127.0.0.1:46120` 无窗口后台运行，并登记为当前 Windows 用户的登录自启项。构建后的页面由 Python 服务从 `frontend\dist` 提供；运行时不需要 Node，也不会加载 CDN。`.runtime\RA2MD` 始终只读，应用不会启动其中的 EXE；所有派生结果进入独立的 `.runtime\RA2MD-Ext`。

页面左侧使用统一树状导航：“单位”下直接选择载具、航空器、步兵和建筑，动画、语音和音效是同级内容节点，不再设置“资源 / 单位”切换或重复的原始模型分类。地图、图像、地形、规则文本及其他底层格式可在显示设置中按需启用。中栏按当前类型提供格式或语义标签以及名称、体积、造价、生命值等有效排序；list/grid 共用查询、筛选、选中与增量分页状态。详情根据类型切换为三维模型、有效帧动画、图像、音频、视频、地图布局或文本。

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
