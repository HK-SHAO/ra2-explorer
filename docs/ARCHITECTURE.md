# RA2 Explorer v0.1 架构

## 运行模型

RA2 Explorer 是单机、只读源数据的本地 Web 应用：

```text
合法安装目录 / Mod 目录
          │ 只读扫描与按需读取
          ▼
格式层（MIX / PAL / SHP）
          │
          ▼
SQLite 索引 ── Python Library ── CLI
                    │
                 FastAPI
                    │ 回环地址
                    ▼
              React 浏览器界面
```

Python 服务是唯一的数据访问入口。CLI 和 HTTP API 都调用 `SourceLibrary`、`AssetReader` 与格式层，不维护第二套解析逻辑。前端生产构建由同一服务提供，因此运行时不需要 Node，也不加载外部 CDN。

## 数据边界

- 用户的源目录只读；扫描器不会改写、移动或解压其中的文件。
- `.runtime/index.sqlite3` 保存索引，`.runtime/reference` 保存可重新下载的文件名数据库。
- 索引记录松散相对路径，或 MIX 根文件与嵌套条目链。导出/预览时重新读取源字节，并检查记录中的 CRC 与大小。
- 第一版不复制完整游戏内容，也不建立内容寻址存储。
- `.runtime`、真实游戏目录、参考仓库、虚拟环境和前端构建产物均不进入 Git。

## 格式支持矩阵

| 格式 | v0.1 能力 | 说明 |
| --- | --- | --- |
| MIX / MMX / YRO | 解析、递归索引、按需读取 | 基础、扩展和 Blowfish 加密索引；同时检测 RA2/TS 与经典哈希 |
| PAL | 解析、网格预览 | 768 字节、256 色、6 位色值扩展到 8 位 |
| SHP (TS/RA2) | 元数据、逐帧 PNG | 支持压缩 0–3、裁剪帧、透明索引 0、可选调色板 |
| INI / CSF / VXL / HVA / TMP / WAV 等 | 索引、搜索、原始导出 | 仅识别；语义解析或渲染在后续版本 |
| 未知条目 | CRC、大小、原始导出 | 文件名未知时显示稳定的 `crc_XXXXXXXX` 名称 |

## MIX 名称与加密

RA2/TS 的文件名标识是对大写文件名执行带特殊尾部填充的 CRC32。早期 Westwood 游戏使用 rotate/add 算法；扫描器根据名称命中情况选择哈希类型，而不是假定所有 MIX 相同。

加密 MIX 先从 80 字节密钥源推导 Blowfish 密钥，再解密索引区。索引、条目范围、嵌套深度、条目数量和根归档大小均有上限与边界校验。损坏的单个归档会作为错误记录，灾难性扫描失败则保留上一版可用索引。

## 本地 API

主要契约：

- `GET /api/sources`、`POST /api/sources`：列出或导入源目录；
- `POST /api/sources/{id}/scan`：原子替换该来源的索引；
- `GET /api/assets`：按来源、名称/路径/CRC 和格式分页检索；
- `GET /api/assets/{id}/content`：导出原始资产；
- `GET /api/assets/{id}/shp`、`preview.png`：读取帧信息与渲染预览；
- `GET /api/palettes`、`GET /api/stats`：辅助浏览；
- `POST /api/demo`：创建无商业素材的合成资料库；
- `POST /api/reference-data/names/sync`：同步固定提交的名称数据库。

OpenAPI 页面在 `/api/docs`。服务拒绝非本机 Host，CLI 也拒绝监听非回环地址。第一版不包含认证，因此不得通过反向代理暴露到局域网或公网。

## 资源与可靠性限制

- 根 MIX 最大 1 GiB、单归档最多 4096 个条目、嵌套最大 6 层；这些是首版的防御性限制，不是格式极限。
- 搜索 API 单次最多返回 500 条，适合交互检索而非全库批量导出。
- 预览会把单个资产读入内存；尚无超大文件流式解码或后台任务队列。
- 已在合成的基础/扩展/加密/嵌套 MIX 与 SHP 压缩样本上验证；由于本机没有合法安装，真实 RA2/YR 全量目录 smoke test 仍待用户安装后执行。
- VXL/HVA、TMP/MAP、CSF/INI 语义与音视频渲染尚未实现。

## 参考实现与可重复数据

格式行为交叉核对了 OpenRA、`iron-curtain-engine/cnc-formats` 和 `ra2web/ra2web-studio`。运行时名称库固定在 `cnc-formats` 提交 `77da596ed72a1201740e054855bf2ff60640bfa9`，下载清单会记录仓库、文件、提交、时间和条目数量。参考代码仓库仅用于开发核对，不参与应用运行。
