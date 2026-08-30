# GitHub Pages 精简版

## 当前结论

RA2 Explorer 已具备纯静态 GitHub Pages 发行模式。在线版地址是 <https://hansimov.github.io/ra2-explorer/>，只提供最适合快速体验的“单位”和“声音”两棵分类树；地图、地形、规则文件浏览、原始导出和本机目录解析继续由完整本地版提供。

精简版的导航和载入范围由快照清单限定，不继承本地版保存过的其他格式开关。只有快照中实际存在且数量大于零的声音格式会参与分类；缺少的数据接口不会用空的地图、图像、调色板或资源包占位。

Pages 不运行 Python、FastAPI 或 SQLite。发布前由本地解析器把真实安装转换成只读静态快照，前端的静态适配层在浏览器中完成目录读取、简繁/模糊/拼音搜索与补全、明确归属和无阵营筛选、事件筛选、排序、关联查询和详情请求。VXL 详情仍由 Three.js 交互渲染，SHP 与卡片使用预生成 WebP，声音按需播放 24 kbit/s Opus。

## 数据边界与实测体积

当前固定快照 `ra2md-slim-0c56a01b33e8` 包含：

| 内容 | 数量或字节 | 约合 |
| --- | ---: | ---: |
| 单位 | 559 | — |
| 声音 | 3,322 | — |
| 发布文件 | 28,967 | — |
| 解包后的 Pages 数据 | 144,037,066 字节 | 137.4 MiB |
| 固定数据 ZIP | 79,220,842 字节 | 75.6 MiB |
| ZIP SHA-256 | `1c8f7b715a50af8930b604d573896a7bb4b881c1789a8eb53b8955c13132687c` | — |

解包数据按用途分布如下：

| 目录 | 字节 | 用途 |
| --- | ---: | --- |
| `previews` | 39,580,930 | 单位、主体动作与建筑图层 WebP |
| `models` | 41,886,903 | 可交互 VXL/HVA 场景 JSON |
| `audio` | 24,774,611 | Opus 声音 |
| `assets` | 19,228,101 | 资产元数据和关联 |
| `entities` | 13,407,158 | 简体/繁体单位详情 |
| `catalog` | 5,159,190 | 简体/繁体单位与声音目录 |

站点不会启动时下载这 137.4 MiB。JavaScript、CSS、当前语言目录、可见卡片、选中详情和用户实际播放的声音分别延迟请求。一次 Playwright 验收覆盖了单位列表、grid 预览、搜索并打开“战斗要塞”、加载交互模型、进入声音并播放一项、打开设置，实测传输约 0.88 MiB、浏览器解码内容约 5.12 MiB。不同 CDN 压缩、浏览器缓存和所选单位会改变实际数字；完整遍历所有资源的最坏上界仍约为 137.4 MiB。

GitHub 官方给出的 Pages 限制包括：发布站点最大 1 GB、每月 100 GB 软带宽限制、部署最长 10 分钟。当前站点约占容量上限的 14%；如果每位访客真的完整遍历全部资源，100 GB 约支持 745 次完整传输，而常规按需会话远低于这一流量。[GitHub Pages 限制](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/github-pages-limits)

## 为什么大数据不进入主分支

主分支只追踪前端、导出器、审计脚本和不足 1 KiB 的 `packaging/pages-data.json`。75.6 MiB ZIP 存放在现有的公开 Hugging Face 发布仓库 `rockstarengine/ra2-explorer-release` 的 `pages-data/pages-data-v1/`，并由提交 `7851b064f7bff9362174b98e33bc0b4a194dd6f2` 固定。这个仓库的 Space 运行时保持暂停；文件下载不启动容器，也不消耗 CPU Basic 配额。

Pages workflow 默认从 `https://hf-mirror.com` 下载，网络失败才回退 `https://huggingface.co`。下载后必须依次通过固定字节数、SHA-256、ZIP 路径安全、文件类型白名单、原始游戏格式禁令、清单计数和隐私扫描，之后才允许解包进站点 artifact。代码版本更新不会重新上传数据；只有解析结果、模型或声音实际变化时才发布新快照并更新锁定清单。

## 构建与发布

本机重建快照：

```bat
.venv\Scripts\ra2exp.exe pages export SOURCE_ID --audio-bitrate 24k --workers 4 --overwrite
```

该命令会原子替换快照目录并自动生成 `.runtime\RA2MD-Ext\pages\RA2-Explorer-Pages-Data.zip`。渲染算法升级时必须递增快照的 render revision，使新快照 ID 不再复用旧版 WebP；压缩过程每 2,000 个文件输出一次进度，避免长时间没有反馈。

审计最终 ZIP：

```bat
.venv\Scripts\python.exe scripts\verify_pages_snapshot.py ".runtime\RA2MD-Ext\pages\RA2-Explorer-Pages-Data.zip"
```

只有数据发生变化时才上传，并原子更新小型锁定清单：

```bat
.venv\Scripts\python.exe scripts\publish_pages_snapshot.py ".runtime\RA2MD-Ext\pages\RA2-Explorer-Pages-Data.zip"
```

前端静态构建和本机预览：

```bat
cd frontend
npm run build:pages
npm run preview:pages -- --host 127.0.0.1 --port 46131 --strictPort
```

`.github\workflows\pages.yml` 在 `master` 的 Pages 前端、数据锁或部署脚本发生变化时运行，也支持手动触发。它使用官方 `configure-pages@v5`、`upload-pages-artifact@v4` 和 `deploy-pages@v4`；上传前会同时确认静态入口、前端 bundle 和数据清单存在，避免只发布数据目录。工作流会完整取回标签：当前提交正好对应 `v*` 标签时，设置正文顶部的信息栏显示稳定版标签；其他提交显示八位 commit，并始终显示该提交的更新时间。部署 job 具有 `pages: write` 与 `id-token: write`，并使用 `github-pages` environment。[GitHub 自定义 Pages workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

该工作流的 `run` shell 是 `cmd`。Runner 会把多行命令写入临时批处理，因此调用 `npm.cmd` 必须使用 `call npm ...` 返回父批处理；否则第一条 npm 命令成功后，后续构建命令不会执行。

如果仓库从未启用 Pages，需要维护者只做一次：Settings → Pages → Build and deployment → Source 选择 GitHub Actions。此后每次前端稳定提交都会自动部署，数据快照仍保持固定，直到明确发布下一版。

## 已实施的流量优化

- 只发布单位和声音，不发布地图、地形、视频、规则全文或原始归档；
- SHP、单位卡片与效果使用 WebP，声音统一转为低码率 Opus；
- 只生成规则确实引用到的动画帧和方向组合；
- 只导出可与当前主体可靠对齐的主体、建造和运行图层；断点复用结束后清理已不再引用的效果资产；
- VXL 卡片只预生成一个标准角度，详情才加载可自由旋转的场景；
- 卡片只请求快照实际导出的朝向；无独立朝向的主体使用固定预览，步兵方向仍跟随默认角度；
- 简体、繁体目录分离，模型、声音和详情完全按需；
- 数据存放在固定提交，代码发布不产生重复的大文件历史。

进一步下降体积时，优先考虑把体素 JSON 改为量化二进制并使用 meshopt、拆分声音目录索引、对共享元数据去重，以及为静态资源增加内容寻址文件名。不要用“启动时把全部资源读进内存”换取速度：那会显著增加移动设备内存、首次流量和主线程解析时间。
