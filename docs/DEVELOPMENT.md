# 开发指南

本文只面向 RA2 Explorer 的开发、测试和发布维护。普通用户请阅读根目录 [README](../README.md)。

## 环境

- Windows x64；
- Python 3.11 或更高版本；
- Node.js 18 或更高版本；
- 所有项目、构建、测试和 Git 命令都在 `cmd.exe` 中运行；
- 真实游戏目录只作为只读测试输入，任何流程都不得运行其中的 EXE、DLL、脚本或安装器。

初始化：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .[dev,release]
cd frontend
npm ci
cd ..
scripts\setup_dev.cmd
```

`setup_dev.cmd` 会把仓库内的隐私检查安装为 Git pre-commit hook。

## 本地资料

约定目录：

```text
.runtime\RA2MD       官方安装，只读
.runtime\RA2MD-Ext   SQLite、参考数据与全部派生结果
```

同步固定来源的文件名库和声音转录，再导入本地安装：

```bat
.venv\Scripts\ra2exp.exe sync-names
.venv\Scripts\ra2exp.exe sync-audio-text
.venv\Scripts\ra2exp.exe import .runtime\RA2MD --name 本地游戏文件
```

普通读取不会永久复制 MIX 成员。只有显式 `extract` 会建立原始成员副本：

```bat
.venv\Scripts\ra2exp.exe cache stats
.venv\Scripts\ra2exp.exe extract SOURCE_ID --format vxl --limit 20
.venv\Scripts\ra2exp.exe cache prune
```

备份当前资料库已经生成的索引和浏览器产物时使用派生资源包；它不会复制原始游戏成员：

```bat
.venv\Scripts\ra2exp.exe resource-pack export SOURCE_ID
.venv\Scripts\ra2exp.exe resource-pack import ".runtime\RA2MD-Ext\packages\PACKAGE.ra2pack"
```

资源包的白名单和离线能力边界见 [派生资源包说明](RESOURCE_PACKS.md)。

## 开发服务

构建前端并安装本机后台服务：

```bat
cd frontend
npm run build
cd ..
.venv\Scripts\ra2exp.exe background install
```

服务固定监听 `http://127.0.0.1:46120`。常用管理命令：

```bat
.venv\Scripts\ra2exp.exe background status
.venv\Scripts\ra2exp.exe background stop
.venv\Scripts\ra2exp.exe background start
.venv\Scripts\ra2exp.exe background uninstall
```

前端热更新在 `frontend` 目录运行 `npm run dev`，代理到 46120。只调试 API 时可运行：

```bat
.venv\Scripts\ra2exp.exe serve
```

该命令默认不打开外部程序；只有显式增加 `--open-browser` 才打开浏览器。

## 验证

```bat
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check src tests packaging\hooks
cd frontend
npm run build
cd ..
.venv\Scripts\python.exe scripts\privacy_scan.py --mode tracked
.venv\Scripts\python.exe scripts\privacy_scan.py --mode history
```

真实安装的重点 smoke test：

```bat
.venv\Scripts\ra2exp.exe verify SOURCE_ID --samples-per-format 20
.venv\Scripts\ra2exp.exe semantic-check SOURCE_ID
.venv\Scripts\ra2exp.exe entities SOURCE_ID --query APOC
.venv\Scripts\ra2exp.exe entities SOURCE_ID --missing
```

## 构建发行包

构建不含游戏数据的公共本地 Web 应用：

```bat
scripts\build_windows.cmd
```

为当前电脑预建索引但不复制游戏目录：

```bat
scripts\build_windows.cmd --game-dir ".runtime\RA2MD"
```

只有经过明确授权的本地场景才构建完整便携素材包：

```bat
scripts\build_windows.cmd --game-dir ".runtime\RA2MD" --include-game-data
```

带 `v*` 的 Git tag 会触发 `.github\workflows\release.yml`，运行测试、隐私扫描、参考数据同步、Windows 构建和 CLI smoke test；随后创建 GitHub Release，并把同一 ZIP、版本清单和 Docker Space 运行文件原子同步到 Hugging Face。手动运行 workflow 只生成可下载的 Actions artifact，不创建 Release。

首次部署 Space 前，维护者需要先上传一份通过白名单校验的派生资源包。凭据只从 `.secrets\local.env` 或进程环境读取，不得写入命令参数、日志或仓库。上传器会切成 4 MiB 内容寻址分片并小批提交，避免依赖受限网络中的 LFS/Xet 上传域；重复运行会跳过已有分片，从网络中断处继续：

```bat
.venv\Scripts\python.exe scripts\publish_hf_release.py --resource-pack ".runtime\RA2MD-Ext\packages\PACKAGE.ra2pack"
```

单独检查 Space 构建上下文时运行：

```bat
.venv\Scripts\python.exe scripts\prepare_hf_space.py --overwrite
```

输出位于被 Git 忽略的 `.outputs\huggingface-space`，只包含 Docker 配置、MIT 许可证、应用 wheel、编译后的前端和公开更新通道，不包含项目源码树、测试、开发文档或资源包副本。部署和恢复流程见 [Hugging Face 部署说明](HUGGINGFACE.md)。

更完整的模块、格式、缓存和 UI 边界见 [架构说明](ARCHITECTURE.md)，发行模式与体积预算见 [发行说明](DISTRIBUTION.md)。
