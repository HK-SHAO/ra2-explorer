# 发行与体积说明

## 发行形态

RA2 Explorer 维护两种互补发行物：

| 发行物 | 入口 | 数据来源 | 适用范围 |
| --- | --- | --- | --- |
| GitHub Pages 精简版 | <https://hansimov.github.io/ra2-explorer/> | 预生成的单位与声音派生快照 | 无需安装的在线体验 |
| Windows 本地 Web 应用 | [GitHub Releases](https://github.com/Hansimov/ra2-explorer/releases) | 用户自己的官方安装或 `.ra2pack` | 完整解析、地图、导出与离线使用 |

两者都使用同一套 React 界面。Pages 在浏览器中读取静态目录和派生媒体；本地版使用现有 Edge/Chrome，加上负责 MIX 内存映射、SQLite 索引、音频解码和图像/体素渲染的小型本地 Python 服务。项目不附带 Electron、Chromium、WebView 或游戏程序。

## Windows 三种构建模式

| 模式 | 命令 | 游戏数据 | 用途 |
| --- | --- | --- | --- |
| `generic` | `ra2exp package` | 不包含 | GitHub Release 与普通用户下载 |
| `linked` | `ra2exp package --game-dir PATH` | 只读关联原路径 | 当前电脑预建完整索引 |
| `portable` | 再加 `--include-game-data` | 复制支持的数据格式 | 获得单独授权的本地场景 |

`portable` 会排除 EXE、DLL、BAT、CMD、COM、MSI、SYS、SCR、LNK 和 PIF。它不会运行游戏程序，但仍可能包含受权利约束的素材，因此默认发布 workflow 永远不构建或上传该模式。

发行目录审计只允许两个启动程序、`_internal` 运行依赖、编译前端、MIT `LICENSE`、简短 `README.txt`、运行标记和可选 `.runtime`。源码、项目开发文档、测试、构建脚本、Git 元数据、Node 依赖、source map 与 TypeScript/Python 源文件都会使构建失败。
第三方运行依赖在 `.dist-info` 中附带的许可证与告知文件会保留，但不会因此放行其他 Markdown 或开发文件。

## 实测体积

以下数据来自 2026-08-30 至 2026-08-31 的 Windows x64 / Python 3.13 构建：

| 项目 | 字节 | 约合 |
| --- | ---: | ---: |
| 公共 `generic` 解压目录 | 49,651,217 | 47.3 MiB |
| 公共 Windows ZIP | 28,860,063 | 27.5 MiB |
| 完整索引的 `linked` 目录 | 58,024,576 | 55.3 MiB |
| 本机安装中可识别的数据 | 668,107,876 | 637.2 MiB |
| 可选 `portable` 解压目录 | 726,161,486 | 692.5 MiB |
| Pages 固定数据 ZIP | 88,881,603 | 84.8 MiB |
| Pages 解包数据 | 148,210,866 | 141.3 MiB |

普通本地用户首次下载约 27.5 MiB；游戏数据从本机读取，不产生网络流量，也不会再次复制约 600 MiB MIX。Pages 访客不会下载数据 ZIP，而是按需请求当前目录、卡片、详情、模型和播放的声音。当前完整交互 smoke 会话实测约 0.88 MiB，完整遍历的理论上界约 141.3 MiB。具体构成和 GitHub 配额分析见 [GitHub Pages 精简版](GITHUB_PAGES.md)。

GitHub Releases 的单个资产必须小于 2 GiB，单个 Release 最多 1,000 个资产；官方文档说明 Release 总大小和带宽没有额外限制。当前 Windows ZIP 远低于限制：[GitHub Releases 官方说明](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。

## 大文件与版本隔离

主分支不追踪游戏文件、`.ra2pack`、Pages 数据 ZIP 或 30,730 个静态派生文件。Pages 只追踪 `packaging/pages-data.json`，其中固定公开 HF 发布仓库、不可变 revision、文件路径、字节数和 SHA-256；代码更新继续复用同一数据快照。只有语义、模型、声音或预览实际变化时，才通过 `scripts\publish_pages_snapshot.py` 发布新快照并更新锁定清单。

本机 `.ra2pack` 位于被 Git 与 Windows 公共构建排除的 `.runtime\RA2MD-Ext\packages`。格式白名单和可迁移能力边界见 [派生资源包说明](RESOURCE_PACKS.md)。

## 自动发布

`.github\workflows\release.yml` 在 Windows runner 和 `cmd.exe` 中完成测试、Ruff、隐私扫描、`generic` 构建、CLI smoke、ZIP、attestation 与 GitHub Release。tag 发布成功后，同一 Windows ZIP 和版本清单会同步到 Hugging Face 文件镜像；不会构建或启动 HF Space 运行时。

`.github\workflows\pages.yml` 下载固定的 Pages 数据 ZIP，先做 SHA-256、路径、文件白名单、统计和隐私审计，再编译静态前端、解包数据并通过官方 Pages actions 发布。前端代码更新不重新上传 Pages 大数据。

公共发布前仍建议为两个 EXE 进行 Authenticode 签名；没有代码签名时，Windows SmartScreen 可能显示未知发布者提示。

> EA has not endorsed and does not support this product.
