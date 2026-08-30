# 发行与体积说明

## 结论

RA2 Explorer 作为本地 Web 应用发布，不使用 GitHub Pages，也不采用 Electron 或嵌入式 WebView。用户界面运行在现有 Edge/Chrome 中；随包附带的小型本地服务负责浏览器沙箱无法完成的任意安装目录读取、MIX 内存映射、SQLite 索引、音频解码和图像/体素渲染。

公共下载只包含程序和非游戏参考数据。用户首次打开时直接关联自己的官方安装，因此不需要再次下载或复制约 600 MiB 游戏归档。

本机另可导出 `.ra2pack` 来备份已生成的索引、关联、预览和转码媒体。该目录位于被 Git 与发行构建排除的 `.runtime\RA2MD-Ext\packages`，不会进入公共下载；详见 [派生资源包说明](RESOURCE_PACKS.md)。

## 三种构建模式

| 模式 | 命令 | 游戏数据 | 适用范围 | 用途 |
| --- | --- | --- | --- | --- |
| `generic` | `ra2exp package` | 不包含 | 任意电脑 | GitHub Release 与普通用户下载 |
| `linked` | `ra2exp package --game-dir PATH` | 只读关联原路径 | 当前电脑 | 同一台电脑预建完整索引 |
| `portable` | 再加 `--include-game-data` | 复制支持的数据格式 | 取决于素材授权 | 可移动的本地素材包 |

`portable` 会排除 EXE、DLL、BAT、CMD、COM、MSI、SYS、SCR、LNK 和 PIF。它不会运行游戏程序，但仍可能包含受权利约束的素材，因此默认发布 workflow 永远不构建或上传该模式。

## 实测体积与流量

以下数据来自 2026-08-30 的 Windows x64 / Python 3.13 构建：

| 项目 | 字节 | 约合 |
| --- | ---: | ---: |
| 公共 `generic` 解压目录 | 49,586,726 | 47.3 MiB |
| 公共 ZIP | 28,806,600 | 27.5 MiB |
| 完整索引的 `linked` 目录 | 58,024,576 | 55.3 MiB |
| 本机安装中可识别的数据 | 668,107,876 | 637.2 MiB |
| 可选 `portable` 解压目录 | 726,161,486 | 692.5 MiB |

因此普通用户的首次下载流量约为 27.5 MiB；1,000 次完整下载约为 26.8 GiB。游戏数据从本机读取，不产生网络流量。预览与转码缓存也只在本机按需生成。

GitHub Releases 的单个资产必须小于 2 GiB，单个 Release 最多 1,000 个资产；官方文档同时说明 Release 的总大小和带宽没有额外限制。当前公共 ZIP 远低于单资产上限，适合通过 Release 分发：[GitHub Releases 官方说明](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。

## 已实施的体积优化

- 不附带游戏归档，默认只建立只读关联；
- 不附带 Electron、Chromium、WebView、Playwright 或 FFmpeg；
- PyInstaller 使用 one-folder，GUI 启动器与 CLI 共享 `_internal`；
- OpenCC 只保留简繁检索需要的两套配置和九个词典文件，不附带开发头文件、静态库和三个工具 EXE；
- Pillow 只收集 PCX、PNG 与绘制链实际需要的模块，不附带 AVIF、WebP、色彩管理和 Tk；
- 普通资产读取不再向 `RA2MD-Ext` 重复写出 MIX 成员，显式解包才持久化；
- 前端 Three.js 分块并由浏览器缓存，图片、模型、音频和视频预览按需生成。

一次真实开发缓存清理中，仅删除冗余 `extracted` 副本就回收了 337,182,197 字节，同时保留 256,027,166 字节的模型、预览、音频、视频和元数据缓存。

## 自动发布

`.github\workflows\release.yml` 在 Windows runner 和 `cmd.exe` 中完成：

1. 安装 Python、Node 与锁定的项目依赖；
2. 同步固定来源的 MIX 文件名库和声音转录；
3. 运行后端测试、Ruff、当前树与完整历史隐私扫描；
4. 构建并审计 `generic` 本地 Web 应用；
5. 运行打包后 `ra2exp.exe --help` smoke test；
6. 生成 ZIP；tag 构建才发布 GitHub Release，手动构建只上传 Actions artifact。

发行目录审计会拒绝构建机工作区、用户目录、Python 安装路径和游戏目录泄露，也会拒绝便携游戏目录中的可执行文件。公共发布前仍建议为两个 EXE 进行 Authenticode 签名；没有代码签名时，Windows SmartScreen 可能显示未知发布者提示。

> EA has not endorsed and does not support this product.
