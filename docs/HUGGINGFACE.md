# Hugging Face 部署

## 采用 Docker Space

RA2 Explorer 的完整在线版本使用 Hugging Face Docker Space，而不是 Static HTML Space。静态 Space 可以托管 React/Vite 的 HTML、CSS 和 JavaScript，但当前应用还依赖以下服务端能力：

- Python 实现的 MIX、SHP、VXL、HVA、AUD、BAG、CSF、INI 与地图解析；
- SQLite 索引、规则/ART/声音语义关系和简繁检索；
- 动态模型 JSON、PNG、WAV 与视频响应；
- 浏览器无权直接遍历的任意 Windows 游戏安装目录。

要变成真正的纯静态应用，需要把解析器和查询层迁移到 JavaScript/WASM，或预先导出全部 API 响应并设计浏览器端数据库。这是可行的独立演进方向，但不是把现有 `dist` 上传后就能保留完整功能。Hugging Face 官方分别说明了 [Static HTML Space](https://huggingface.co/docs/hub/spaces-sdks-static)、[Docker Space](https://huggingface.co/docs/hub/main/spaces-sdks-docker) 和 [Space YAML 配置](https://huggingface.co/docs/hub/main/spaces-config-reference)。

## 运行边界

Docker 镜像采用两个阶段：

1. 构建阶段安装应用 wheel，按 SHA-256 校验并组合 `resources/default.ra2pack.parts/`，再把资源包解包成索引和派生产物；
2. 运行阶段只复制解包结果、应用运行依赖和编译后的前端，不复制 `.ra2pack` 本身，也不复制项目源码树、测试或开发文档。

容器以非 root 用户运行，监听 Space 规定的 `7860` 端口，并设置 `RA2_EXPLORER_HOSTED=1`。托管模式关闭 OpenAPI 和全部写操作；本地应用仍只监听 `127.0.0.1:46120`，保留目录解析、重扫、导入和导出功能。Space 文件系统重启后可以从镜像中的预置快照恢复，不依赖持久卷。

当前派生包约 178.1 MiB，解压后的浏览器产物约 264.8 MiB。它只存放一次并在镜像构建时展开；访问者不会下载整个包。网页端约 0.7 MiB 的前端按普通 HTTP 缓存，预览和媒体按需请求。高性能预载也采用“当前单位分类持久缓存 + 当前/相邻模型有界内存 LRU”，避免一次性解析全部模型导致长时间占用主线程或耗尽移动设备内存。

## 发布流程

Space 仓库需要预先配置为公开仓库，并在 GitHub Actions 中保存 `HF_TOKEN_RELEASE` 和 `HF_SPACE_RELEASE_REPO`。Token 只用于官方 Hugging Face 写入端点；对用户公开的更新读取默认走 `https://hf-mirror.com`。

首次或更换资料快照时，从本机被 Git 忽略的派生目录上传：

```bat
.venv\Scripts\python.exe scripts\publish_hf_release.py --resource-pack ".runtime\RA2MD-Ext\packages\PACKAGE.ra2pack"
```

脚本只接受 `contains_game_files=false` 的 RA2 Explorer 资源包，并校验安全路径、条目上限、允许扩展名、语义快照、产物数量和字节数。通过后生成 4 MiB 内容寻址分片并小批提交；重复运行会跳过已存在的分片，最后才原子更新总 SHA-256 和激活清单。小分片直接走已验证可达的 Hub Git API，避免部分国内链路无法连接 LFS/Xet 对象存储时整包卡住，也不必在中断后重传整个约 178 MiB 文件。官方上传接口说明见 [Upload files to the Hub](https://huggingface.co/docs/huggingface_hub/en/guides/upload)。

首次资源上传完成后，可以不创建应用 Release，单独激活或修复已经审计的 Space 运行文件：

```bat
.venv\Scripts\python.exe scripts\publish_hf_release.py --space-bundle ".outputs\huggingface-space"
```

正常版本发布只需推送 `vX.Y.Z` tag。GitHub workflow 会：

1. 重跑全部测试、Ruff 与隐私扫描；
2. 构建并审计 Windows 本地网页应用；
3. 创建 GitHub Release；
4. 生成只含 wheel、前端和 Docker 配置的 Space 上下文；
5. 在一个 Hugging Face commit 中同步 Windows ZIP、SHA-256 清单和 Space 运行文件。

同步计划不会删除 `.gitattributes`、`resources/` 或旧版 `releases/`。若资源分片或总 SHA-256 尚未存在，发布会明确失败，避免把无法启动的 Docker 配置推到 Space。

## 恢复与更新

- 应用 BUG、性能和 UI 更新：发布新 tag；用户可以在设置中自行检查并选择下载，本地 `.runtime` 保留。
- 只更新在线资料：重新运行 `--resource-pack` 上传，再由 Space 自动重建镜像。
- Space 构建失败：查看 Space build log；修复后重新发布 tag，或手动用同一脚本同步已审计的上下文。
- HF 镜像不可用：本地应用的更新检查仅在网络失败时回退 GitHub，不会因为无效清单而降级接受未经验证的地址。
