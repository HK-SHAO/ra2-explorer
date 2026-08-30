# 实际解析输入

RA2 Explorer 不会执行安装目录中的任何程序。扫描器只读取受支持的松散资源文件，以及 `.mix`、`.mmx`、`.yro` 归档和其中最多四层的嵌套归档。

## 当前官方尤里复仇安装

2026-08-30 对本项目本机官方安装的实际索引结果为 16,820 个资产。顶层会进入归档扫描的文件是：

```text
amazon.mmx
EB1.mmx … EB5.mmx
expandmd01.mix
invasion.mmx
langmd.mix
language.mix
MAPSMD03.MIX
movmd03.mix
MULTIMD.MIX
ra2.mix
ra2md.mix
thememd.mix
```

其中 `movmd03.mix` 与 `thememd.mix` 在这份安装中是五字节 CD class marker，扫描器会识别并计数，但不会误报为损坏归档。归档内还解析出 `local.mix`、`LOCALMD.MIX` 等嵌套归档，总计 64 个归档记录；资产列表中另有 48 项可继续作为 MIX 资源查看。

建立单位、事件和文本关系时，真正作为配置输入的文件如下；后出现的资料片/扩展条目按优先级覆盖基础条目：

| 用途 | 实际虚拟路径 |
| --- | --- |
| 基础规则 | `ra2.mix/local.mix::rules.ini` |
| 尤里规则 | `ra2md.mix/LOCALMD.MIX::RULESMD.INI` |
| 扩展规则 | `expandmd01.mix::RULESMD.INI` |
| 基础美术映射 | `ra2.mix/local.mix::art.ini` |
| 尤里美术映射 | `ra2md.mix/LOCALMD.MIX::ARTMD.INI` |
| 基础声音事件 | `ra2.mix/local.mix::SOUND.INI` |
| 尤里声音事件 | `ra2md.mix/LOCALMD.MIX::SOUNDMD.INI` |
| 扩展声音事件 | `expandmd01.mix::SOUNDMD.INI` |
| 基础 EVA 事件 | `ra2.mix/local.mix::EVA.INI` |
| 尤里 EVA 事件 | `ra2md.mix/LOCALMD.MIX::EVAMD.INI` |
| 基础本地化 | `language.mix::ra2.csf` |
| 尤里本地化 | `langmd.mix::RA2MD.CSF` |

## 按需读取的主体与媒体

配置合并后，应用再按规则中的 `Image`、`Cameo`、`Sequence`、`Voice*`、`Sound*`、武器和弹头字段，从完整索引中解析实际引用的资源：

- 单位与部件：VXL、HVA、SHP、PCX；
- 外观：PAL 与 `voxels.vpl`；
- 声音：WAV、AUD、BAG/IDX 中的音频片段；
- 场景：MAP/MPR、TMP/TEM/SNO/URB/UBN/LUN/DES；
- 影片：VQA/BIK；
- 辅助数据：INI、CSF、FNT 和 TXT。

因此并非 16,820 个资产都会在启动时完整解码。首次扫描主要建立归档和格式索引；只有列表、详情、预览或播放真正引用某项时，才读取相应 MIX 区段并产生浏览器缓存。

`known_names_ra2.txt`、声音转录表和任务对白补充表位于 `RA2MD-Ext/reference`。它们用于恢复 MIX 名称或补充检索文本，不是游戏源文件，也不会覆盖游戏规则本身。
