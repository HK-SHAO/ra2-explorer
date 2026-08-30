# 派生资源包

RA2 Explorer 可以把当前资料库的索引、语义关联和已经生成的浏览器产物导出为 `.ra2pack`。资源包用于在本机备份或迁移解析结果，导入后无需重新扫描原版游戏目录即可复用其中已有的预览和媒体。

## 包含范围

资源包只允许以下内容：

- 去除本机根路径的 SQLite 索引快照；
- 单位、声音、文本和事件关系的语义索引；
- 已生成的 PNG 预览、模型 JSON、浏览器 WAV 与 MP4；
- 预览所需的派生元数据。

它明确排除 MIX、SHP、VXL、HVA、INI、CSF、PAL、VPL、AUD 等原始游戏文件，也排除 `extracted` 原始成员副本。导入器会校验目录穿越、符号链接、加密条目、文件类型、条目数量和解压体积；出现未知文件时会拒绝整个包。

资源包保存的是导出时已经实际生成的内容，不会为了导出而批量渲染整个游戏。这样可避免重新形成约 600 MiB 的游戏副本。若导入后访问到从未生成过的预览，应用会提示重新导入原版目录；浏览相应内容后再次导出即可逐步完善资源包。

## 命令行

先用 `ra2exp sources` 找到资料库 ID：

```bat
.venv\Scripts\ra2exp.exe resource-pack export SOURCE_ID
.venv\Scripts\ra2exp.exe resource-pack list
.venv\Scripts\ra2exp.exe resource-pack import "D:\Backups\resources.ra2pack"
```

默认导出位置是 `.runtime\RA2MD-Ext\packages`。也可以在导出时指定文件：

```bat
.venv\Scripts\ra2exp.exe resource-pack export SOURCE_ID --output "D:\Backups\yr-assets.ra2pack"
```

`.runtime` 已被 Git 忽略，默认构建和公开 Release 也不会收集资源包，因此这些本机备份不会随源码或公共程序发布。

## 与发行包的区别

公共 `generic` 发行包只包含程序，适合所有合法安装用户；`.ra2pack` 是某个资料库在特定扫描版本下的本机派生快照。它不包含游戏本体，但其中的图片、声音或模型预览仍可能受原素材权利约束，不应仅因文件已转换就假定可以公开分发。
