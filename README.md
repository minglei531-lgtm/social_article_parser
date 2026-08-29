# 社媒文章清理器

这是一个 Windows 原生桌面工具：粘贴或打开文章 HTML，点击“解析文章”，结果会显示在程序内的 Windows 原生文本框中，可滚动、选中和复制。

界面使用 Windows Forms，不使用 Python Tk 或内嵌大文本结果框。

## 使用

双击：

```text
启动解析器.cmd
```

或者直接启动：

```text
dist\social_article_parser.exe
```

## 重新打包

在已安装 Python 与 PyInstaller 的 Windows 电脑上运行：

```powershell
.\打包成EXE.ps1
```

它会生成一个单文件 `dist\social_article_parser.exe`。运行时会把精简的解析组件临时释放到系统临时目录；临时 HTML 和 TXT 结果在读取后会立即删除，主窗口与结果查看均为 Windows 原生程序。
