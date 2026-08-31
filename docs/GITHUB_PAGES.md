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
| 解包后的 Pages 数据 | 144,690,082 字节 | 138.0 MiB |
| 固定数据 ZIP | 79,311,508 字节 | 75.6 MiB |
| ZIP SHA-256 | `113f912f001995653de36ef236f5496e773b2a8283425a57b9007cf2c9790a73` | — |

解包数据按用途分布如下：

| 目录 | 字节 | 用途 |
| --- | ---: | --- |
| `previews` | 39,580,930 | 单位、主体动作与建筑图层 WebP |
| `models` | 41,886,903 | 可交互 VXL/HVA 场景 JSON |
| `audio` | 24,774,611 | Opus 声音 |
| `assets` | 19,228,101 | 资产元数据和关联 |
| `entities` | 13,407,158 | 简体/繁体单位详情 |
| `catalog` | 5,812,206 | 简体/繁体单位与声音目录及搜索别名 |

站点不会启动时下载整套 138.0 MiB 数据，也不会把发布 ZIP 发送给访客。单位页启动只读取约 400 KiB 的当前语言单位目录，不再为了侧栏计数提前读取约 2 MiB 的声音目录；可见卡片优先并发，首屏稳定 1.6 秒后才以最多两个后台请求继续预取当前单位分类。交互模型、详情和声音仍按操作加载。不同分类、停留时间、CDN 压缩和浏览器缓存都会改变会话流量，因此不把某一次本机自动化数字当成公开带宽承诺；完整遍历所有资源的理论上界约为 138.0 MiB。

GitHub 官方给出的 Pages 限制包括：发布站点最大 1 GB、每月 100 GB 软带宽限制、部署最长 10 分钟。当前站点约占容量上限的 14%；实际可服务会话数取决于用户打开的分类和 CDN 缓存，不用“ZIP 大小 × 访问量”代替真实监控。[GitHub Pages 限制](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/github-pages-limits)

## 为什么大数据不进入主分支

主分支只追踪前端、导出器、审计脚本和不足 1 KiB 的 `packaging/pages-data.json`。75.6 MiB ZIP 存放在独立的 Hugging Face 文件仓库；锁定清单记录不可变 revision、大小和 SHA-256，是构建使用版本的唯一权威来源。文件下载不依赖或启动 Space 容器。

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

Pages 构建写入独立的 `frontend\dist-pages`，普通本地应用继续使用 `frontend\dist`。两种验证可以依次执行而不会用 `/ra2-explorer/` 的静态入口覆盖本机后台正在提供的根路径，也不会让自动化误等一个实际已经损坏的页面。

`.github\workflows\pages.yml` 在 `master` 的 Pages 前端、数据锁或部署脚本发生变化时运行，也会在推送 `v*` 稳定标签时重建，并支持手动触发。它使用官方 `configure-pages@v5`、`upload-pages-artifact@v4` 和 `deploy-pages@v4`；上传前会同时确认静态入口、前端 bundle 和数据清单存在，避免只发布数据目录。工作流会完整取回标签：当前提交正好对应 `v*` 标签时，设置正文顶部的信息栏显示稳定版标签；其他提交显示八位 commit。版本文字链接到对应的 GitHub commit，并显示该构建相对最新稳定标签提前或落后的提交数及提交时间。部署 job 具有 `pages: write` 与 `id-token: write`，并使用 `github-pages` environment。[GitHub 自定义 Pages workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

该工作流的 `run` shell 是 `cmd`。Runner 会把多行命令写入临时批处理，因此调用 `npm.cmd` 必须使用 `call npm ...` 返回父批处理；否则第一条 npm 命令成功后，后续构建命令不会执行。

如果仓库从未启用 Pages，需要维护者只做一次：Settings → Pages → Build and deployment → Source 选择 GitHub Actions。此后每次前端稳定提交都会自动部署，数据快照仍保持固定，直到明确发布下一版。

## 已实施的流量优化

- 只发布单位和声音，不发布地图、地形、视频、规则全文或原始归档；
- SHP、单位卡片与效果使用 WebP，声音统一转为低码率 Opus；
- 只生成规则确实引用到的动画帧和方向组合；
- 只导出可与当前主体可靠对齐的主体、建造和运行图层；断点复用结束后清理已不再引用的效果资产；
- VXL 卡片只预生成一个标准角度，详情才加载可自由旋转的场景；
- 卡片只请求快照实际导出的朝向；无独立朝向的主体使用固定预览，步兵方向仍跟随默认角度；
- 单位页不为声音计数读取完整声音目录；首屏卡片和后台预取使用独立优先级与有界并发，切换分类时新前台请求可越过旧后台队列；
- 简体、繁体目录分离，模型、声音和详情完全按需；
- 数据存放在固定提交，代码发布不产生重复的大文件历史。

进一步下降体积时，优先考虑把体素 JSON 改为量化二进制并使用 meshopt、拆分声音目录索引、对共享元数据去重，以及为静态资源增加内容寻址文件名。不要用“启动时把全部资源读进内存”换取速度：那会显著增加移动设备内存、首次流量和主线程解析时间。
