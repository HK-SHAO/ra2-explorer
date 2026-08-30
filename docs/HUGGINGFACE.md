# Hugging Face 文件镜像

## 当前状态

Hugging Face Space 的 CPU Basic 免费配额已经达到限制，因此 RA2 Explorer 不再把 Space 运行时作为在线产品入口。现有 Space 保持 `PAUSED`，不会启动 Docker 容器，也不会消耗 CPU 配额。在线体验改由 [GitHub Pages 精简版](GITHUB_PAGES.md) 提供。

Hugging Face 仍承担两种不需要计算资源的稳定文件分发：

- 每个正式版本的 Windows ZIP、SHA-256 和更新清单；
- GitHub Pages 构建使用的固定单位/声音数据 ZIP。

用户版更新默认从 `https://hf-mirror.com` 读取，失败才回退 GitHub。Pages workflow 也先从镜像下载固定数据，失败再回退 `https://huggingface.co`。Token 只发送到 Hugging Face 官方写入 API，绝不会发给镜像或写入仓库。

## 稳定版本同步

推送 `vX.Y.Z` tag 后，`.github\workflows\release.yml` 会：

1. 运行后端测试、Ruff、隐私扫描和前端构建；
2. 构建并审计不含游戏数据的 Windows 本地 Web 应用；
3. 创建 GitHub Release 与 artifact attestation；
4. 把同一 ZIP、版本说明和校验清单同步到 Hugging Face 发布仓库。

workflow 不再准备或同步 Docker Space bundle，因此发布版本不会尝试恢复在线容器。`HF_TOKEN_RELEASE` 和 `HF_SPACE_RELEASE_REPO` 只保存在 GitHub Actions secrets；本地维护时可放在被 Git 忽略的 `.secrets\local.env`。

## Pages 固定数据

当前数据位于公开发布仓库 `rockstarengine/ra2-explorer-release`：

```text
pages-data/pages-data-v1/
├── manifest.json
└── RA2-Explorer-Pages-Data.zip
```

ZIP 由 HF 的文件存储/CDN 提供，不依赖 Space 容器。主分支的 `packaging/pages-data.json` 固定到提交 `5889a23822f00377d9cdf07550d61c94b1dc172e`，因此后续 Space 仓库文件变化不会悄悄改变 Pages 构建输入。

只在派生内容实际变化时重新发布：

```bat
.venv\Scripts\python.exe scripts\publish_pages_snapshot.py ".runtime\RA2MD-Ext\pages\RA2-Explorer-Pages-Data.zip"
```

发布器先运行完整快照审计，再通过官方端点上传 ZIP 和公开清单，最后把新 revision、SHA-256、字节数和资源计数写入 `packaging/pages-data.json`。它不会输出 token。Hugging Face 官方说明 `upload_file`/`create_commit` 支持模型、Dataset 与 Space 仓库，并通过内容存储处理大文件：[HfApi 文档](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api)。

## 历史完整资源包

仓库中原有的 `resources/default.ra2pack.parts/` 是此前 Docker Space 使用的授权派生包分片。它不进入 GitHub 主分支，也不进入 Windows ZIP。Space 保持暂停后，Pages 不读取这份完整资源包；保留它只为以后恢复完整托管或复用已解析结果，不会产生运行费用。

如果未来恢复有配额的服务端托管，可以重新使用 `scripts\prepare_hf_space.py` 和 `scripts\publish_hf_release.py --space-bundle ...`。在明确恢复前，正式发布流程只同步稳定下载文件。
