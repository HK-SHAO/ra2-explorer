# 发行与体积

## 面向用户的发行物

| 发行物 | 入口 | 数据来源 | 适用范围 |
| --- | --- | --- | --- |
| GitHub Pages 精简版 | <https://hansimov.github.io/ra2-explorer/> | 固定单位/声音派生快照 | 无需安装的在线体验 |
| Windows 本地 Web 应用 | [GitHub Releases](https://github.com/Hansimov/ra2-explorer/releases) | 用户自己的官方安装或 `.ra2pack` | 完整解析、地图、导出和离线使用 |

两者共用 React UI。本地版使用系统已有浏览器和一个只监听回环地址的 Python 服务，不附带 Electron、Chromium、WebView 或游戏程序。

## Windows 构建模式

| 模式 | 命令 | 游戏数据 | 可分享性 |
| --- | --- | --- | --- |
| `generic` | `ra2exp package` | 不包含 | 默认公共 Release |
| `linked` | `ra2exp package --game-dir PATH` | 只读关联原路径 | 只适合当前电脑 |
| `portable` | 再加 `--include-game-data` | 复制白名单数据格式 | 仅限明确授权场景 |

`portable` 排除 EXE、DLL、BAT、CMD、COM、MSI、SYS、SCR、LNK 和 PIF；默认 workflow 永远不构建或上传它。

公共目录只允许 `RA2 Explorer.exe`、`ra2exp.exe`、共享 `_internal`、编译前端、公开参考数据、MIT `LICENSE`、简短 `README.txt`、运行标记和公开更新通道。源码、测试、项目文档、Git 元数据、Node 依赖、source map 和构建脚本都会使审计失败；第三方运行依赖在 `.dist-info` 中必须保留的许可证文件除外。

## v0.9 本机构建测量

以下数据来自 Windows x64 generic 生产构建，不含游戏或 `.ra2pack`：

| 项目 | 字节 | 约合 |
| --- | ---: | ---: |
| 解压目录（210 个文件） | 58,495,913 | 55.8 MiB |
| `RA2-Explorer-Web-x64.zip` | 34,959,813 | 33.3 MiB |
| Pages 固定数据 ZIP | 79,220,842 | 75.6 MiB |
| Pages 解包数据 | 144,037,066 | 137.4 MiB |

具体 Release 可能因 Python、依赖或压缩器小幅变化。普通本地用户不会下载或复制数百 MiB 的 MIX；首次导入直接关联本机安装。Pages 访客也不会下载数据 ZIP，而是按页面、预取队列和用户操作请求静态文件。

## 大文件隔离

主分支只追踪代码和 `packaging\pages-data.json`。Pages 数据 ZIP 存放在独立文件仓库并固定到不可变 revision；代码更新继续复用它。`.ra2pack`、游戏文件和本地发行输出均位于被 Git 忽略的目录。

## 自动发布

- `.github\workflows\release.yml` 在 Windows 与 `cmd.exe` 中执行测试、Ruff、隐私扫描、generic 构建、包内容审计、CLI smoke、ZIP、attestation、GitHub Release 和 Hugging Face 镜像同步。
- `.github\workflows\pages.yml` 下载锁定数据，解包前后审计，构建 `frontend\dist-pages` 并通过官方 Pages actions 发布。

公共 EXE 尚未进行 Authenticode 签名时，Windows SmartScreen 可能显示未知发布者。构建来源证明可以核对 workflow 与 commit，但不替代代码签名。

> EA has not endorsed and does not support this product.
