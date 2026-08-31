# Hugging Face 文件镜像

Hugging Face 在本项目中只承担静态文件分发，不运行 RA2 Explorer 服务端或 Space 容器。在线应用由 [GitHub Pages](GITHUB_PAGES.md) 提供。

## 分发内容

公开文件分成两个互不混用的仓库：

- Release Space 的 `releases/`：稳定 Windows ZIP、版本清单、SHA-256 和 Release 说明；
- `rockstarengine/ra2-explorer-pages-data` Dataset：GitHub Pages 使用的固定单位/声音数据 ZIP 与清单。

Windows 更新默认从 `https://hf-mirror.com` 下载，失败后回退 GitHub。Pages workflow 同样先尝试镜像，再回退 `https://huggingface.co`。写入操作只使用 Hugging Face 官方 API；访问 token 不会发送给镜像。

## 稳定版同步

推送 `vX.Y.Z` tag 后，`.github\workflows\release.yml` 会测试并审计源码，构建 generic Windows 包，创建 GitHub Release，然后把同一 ZIP 和版本清单同步到文件仓库。

Actions 需要仓库 secrets：

- `HF_TOKEN_RELEASE`：只授予目标仓库所需的写权限；
- `HF_SPACE_RELEASE_REPO`：历史命名保留的目标仓库标识。

本地维护时可把同名变量放在被 Git 忽略的 `.secrets\local.env`。脚本不得输出 token，也不得把 token 放入命令参数、URL 或构建产物。

## Pages 固定数据

主分支不追踪大型 ZIP。`packaging\pages-data.json` 是唯一权威锁定清单，保存仓库、不可变 revision、路径、大小、SHA-256、快照 ID 和资源计数。文档不复制 revision，避免数据更新后出现多个互相矛盾的版本。

只有派生内容真正变化时才运行：

```bat
.venv\Scripts\python.exe scripts\publish_pages_snapshot.py .runtime\RA2MD-Ext\pages\RA2-Explorer-Pages-Data.zip --repository rockstarengine/ra2-explorer-pages-data --repo-type dataset --create-repository
```

发布器先完成路径安全、格式白名单、原始游戏格式禁令、计数、体积和隐私审计，再上传 ZIP，并原子更新锁定清单。普通 UI、搜索或性能修复继续复用既有快照。

Pages 数据使用独立 Dataset，避免与历代 Windows ZIP 共用 Space 的存储上限。Hugging Face Space 的 CPU 运行配额、Docker bundle 和历史完整资源分片不属于当前发行链路；维护者不应在稳定发布中尝试启动或同步 Space 运行时。
