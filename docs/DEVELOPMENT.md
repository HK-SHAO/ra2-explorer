# 开发指南

本文只面向源码开发与发布维护。普通用户从根目录 [README](../README.md) 开始。

## 环境

- Windows x64；
- Python 3.11 或更高版本；
- Node.js 18 或更高版本；
- 项目、测试、构建和 Git 命令统一在 `cmd.exe` 中运行；
- 游戏安装只作为静态、只读测试输入，禁止运行其中的程序。

初始化：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .[dev,release]
cd frontend
npm ci
cd ..
scripts\setup_dev.cmd
```

最后一条命令启用仓库内的 pre-commit 隐私扫描。

## 本地数据与服务

```text
.runtime\RA2MD       可选的官方安装，只读
.runtime\RA2MD-Ext   索引、参考数据、缓存、测试产物和发行中间结果
```

常用初始化和导入命令：

```bat
.venv\Scripts\ra2exp.exe sync-names
.venv\Scripts\ra2exp.exe sync-audio-text
.venv\Scripts\ra2exp.exe import .runtime\RA2MD --name 本地游戏文件
```

构建前端并安装当前用户后台服务：

```bat
cd frontend
npm run build
cd ..
.venv\Scripts\ra2exp.exe background install
```

服务监听 `http://127.0.0.1:46120`。管理命令是 `background status/start/stop/uninstall`。前端热更新使用 `frontend` 目录的 `npm run dev`；仅调试 API 时使用 `ra2exp serve`，只有显式传入 `--open-browser` 才会调用系统浏览器。

所有可复用派生数据必须写入 `RA2MD-Ext`。普通读取不落盘复制 MIX 成员；只有显式 `extract` 建立原始成员副本，`cache prune` 默认只清理这类可再生成副本。

## 验证

提交前的完整基础验证：

```bat
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check src tests packaging\hooks scripts
cd frontend
npm run build
npm run build:pages
cd ..
.venv\Scripts\python.exe scripts\privacy_scan.py --mode tracked
.venv\Scripts\python.exe scripts\privacy_scan.py --mode history
git diff --check
```

涉及真实格式或语义关系时，再运行：

```bat
.venv\Scripts\ra2exp.exe verify SOURCE_ID --samples-per-format 20
.venv\Scripts\ra2exp.exe semantic-check SOURCE_ID
```

涉及 UI、媒体或性能时使用 Playwright 覆盖真实生产构建，至少检查主流桌面宽度、820px 附近降级、滚动、分类切换、控制台错误和重复网络请求。QA 截图、脚本和 profile 结果只放在 `.runtime\RA2MD-Ext`，不提交到源码。

## Windows 发行

公共包不含游戏数据：

```bat
scripts\build_windows.cmd
```

当前电脑可用 `--game-dir PATH` 预建只读关联索引；只有明确授权的本地场景才再加 `--include-game-data`。默认发布 workflow 永远只构建 generic 包。

推送 `vX.Y.Z` tag 会触发 `.github\workflows\release.yml`，重新执行测试、隐私扫描、Windows 构建、包审计和 CLI smoke，随后创建 GitHub Release。版本号必须同步修改 `pyproject.toml`、`src/ra2_explorer/__init__.py` 和前端 package 文件。

## 静态网页包

只有单位、声音、语义或渲染产物实际变化时才重建数据：

```bat
.venv\Scripts\ra2exp.exe pages export SOURCE_ID --audio-bitrate 24k --workers 8 --overwrite
.venv\Scripts\ra2exp.exe movies build SOURCE_ID
.venv\Scripts\python.exe scripts\verify_pages_snapshot.py .outputs\toy\pages-data.zip
```

`npm run build:pages` 构建静态前端到 `frontend\dist-pages`（相对路径 base），不会覆盖本地版 `frontend\dist`。把快照数据放进 `frontend\dist-pages\data` 后整体打包，即得到可离线浏览、可直接发布到 Toy 的单文件 ZIP。

## 文档与提交

- 根 README 只写用户需要的下载、使用、能力与边界；开发命令留在本文件。
- 架构文档描述当前长期契约，不堆积逐个 bug 的修复经过或下一阶段设想。
- 不提交聊天记录、提示词、个人叙述、本机路径、来源 UUID、临时截图、一次性 profile 或 token。
- 功能稳定并通过对应验证后立即形成小提交；避免把不相关功能、文档清理和发行准备混在一个大提交中。

更多边界见 [架构](ARCHITECTURE.md)、[发行说明](DISTRIBUTION.md) 和 [隐私与发布安全](PRIVACY.md)。
