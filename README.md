# RA2 Explorer

RA2 Explorer 是一个本地优先的《命令与征服：红色警戒 2》资产浏览器。它只读挂载用户自己的游戏目录，把 MIX 中的图像、体素、地形、文本和声音组织成可搜索、可预览、可播放、可导出的本地资产库。

当前可执行边界：

- 扫描本地目录中的松散资产和 MIX / MMX / YRO；
- 读取基础、扩展和 Blowfish 加密 MIX，并递归索引已知的嵌套 MIX；
- 同时解析 RA2/TS CRC32 与早期 Westwood 文件名哈希；
- 预览 PAL、RA2/TS SHP、VXL 体素部件、TMP 地块和 PCX；
- 读取 HVA 矩阵、CSF/INI/MAP 文本，并在浏览器播放 PCM 或 IMA ADPCM WAV；
- 自动发现项目内 `.runtime\RA2MD`、Steam App 2229850、EA App/Origin 与兼容旧版安装；
- 对真实来源按格式均匀抽样，执行解析和首帧渲染验证；
- 通过 SQLite、HTTP API、CLI 和浏览器界面访问同一份索引；
- 生成不包含 EA 内容的本地演示资产库。

项目不会附带或自动上传商业游戏文件。当前官方 PC 版本是 Steam / EA App 中的 *Command & Conquer Red Alert 2 and Yuri's Revenge*；导入前需要由用户在相应平台合法安装。

## 立即运行

开发、构建、测试、检查和运行命令强制使用 `cmd.exe`；只有 Git 操作使用 Git Bash。以下命令均为 `cmd.exe` 语法，要求 Python 3.11+ 和 Node 18+：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .[dev]
.venv\Scripts\ra2-explorer.exe sync-names
.venv\Scripts\ra2-explorer.exe demo
cd frontend
npm ci
npm run build
cd ..
.venv\Scripts\ra2-explorer.exe background install
```

服务在 `http://127.0.0.1:46120` 无窗口后台运行，并登记为当前 Windows 用户的登录自启项。构建后的页面由 Python 服务从 `frontend\dist` 提供；运行时不需要 Node，也不会加载 CDN。首次可直接浏览合成格式样本，再从页面添加自己的合法游戏目录。扫描和预览只读取文件字节，不会启动游戏目录中的 EXE。

只开发 API 时可以不构建前端，接口文档位于 `http://127.0.0.1:46120/api/docs`。前端热更新使用 `cd frontend` 后运行 `npm run dev`。后台管理命令为：

```bat
.venv\Scripts\ra2-explorer.exe background status
.venv\Scripts\ra2-explorer.exe background stop
.venv\Scripts\ra2-explorer.exe background start
.venv\Scripts\ra2-explorer.exe background uninstall
```

交互式调试可运行 `.venv\Scripts\ra2-explorer.exe serve`；它默认不会调用 Windows 外部程序。如确实需要自动打开浏览器，显式增加 `--open-browser`。

## 验证

```bat
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\ra2-explorer.exe verify <source-id> --samples-per-format 20
cd frontend
npm run build
```

真实 RA2 文件只用于本地 smoke test，不进入仓库。架构与导入边界见 [v0.2 架构](docs/ARCHITECTURE.md)，合法游戏来源、本机导入和无游戏文件时的格式样本方案见 [获取与导入游戏文件](docs/GAME_FILES.md)。

## 权利边界

RA2 Explorer 与 Electronic Arts 或其许可方无隶属或背书关系。游戏内容的提取、派生、上传和发布权限取决于用户所在地法律、平台条款以及具体素材权利；音乐、角色语音和第三方 Mod 资产应单独确认授权。
