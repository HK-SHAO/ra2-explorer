# 获取与导入游戏文件

RA2 Explorer 不附带《红色警戒 2 / 尤里的复仇》的原始游戏文件。本地完整版需要用户自己拥有并安装合法版本；在线精简版无需本地游戏。

## 合法安装来源

可使用以下安装之一：

- [Steam 的 Red Alert 2 and Yuri's Revenge 商店页](https://store.steampowered.com/app/2229850/Command__Conquer_Red_Alert_2_and_Yuris_Revenge/)；
- EA App 中的 *Command & Conquer The Ultimate Collection*；
- 用户已有且当前 Windows 能读取的兼容零售安装。

[CnCNet 的 Windows 指南](https://cncnet.org/red-alert-2/how-to-play) 可用于现代系统兼容和联网，但不能替代游戏所有权。项目不会从非授权镜像或所谓“免安装版”自动下载商业内容。

## 在应用中导入

1. 打开左下角“设置”。
2. 在“游戏目录”中选择自动发现的安装，或填写包含 `ra2.mix` / `ra2md.mix` 的目录。
3. 开始解析并等待索引完成。

程序会读取 Steam 库清单、EA/Westwood 注册表和常见 EA App/Origin 目录，但只有实际找到 RA2/YR 根归档时才显示候选。源文件始终只读；索引、预览、转码媒体和模型写入应用目录的 `.runtime\RA2MD-Ext`。

如果移动了游戏目录，重新选择新路径并扫描即可。不要把 `RA2MD-Ext` 选作游戏目录，它只包含派生结果且会被扫描器排除。

## 可选命令行

开发版或已安装 CLI 可以执行同样的只读流程：

```bat
ra2exp.exe discover
ra2exp.exe import PATH_TO_GAME --name 本地游戏文件
ra2exp.exe sources
ra2exp.exe verify SOURCE_ID --samples-per-format 20
```

`discover` 只报告候选，不启动游戏。`verify` 抽样读取并解码格式，不执行安装目录中的程序。

## 文件名参考数据

部分 MIX 条目只保存 CRC。维护环境可运行 `ra2exp.exe sync-names`，把固定版本的公开文件名数据库下载到 `.runtime\reference`；它只帮助恢复名称，不包含游戏素材。声音转录使用独立的 `sync-audio-text`，同样不会改写游戏安装。

真正参与规则、单位、声音和本地化解析的文件见 [游戏源输入](GAME_SOURCE_INPUTS.md)。
