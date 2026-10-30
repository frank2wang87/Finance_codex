# 投资手记：启动与使用

这是本地运行的投资记录工具。网页地址为 <http://127.0.0.1:8765>，数据保存在项目目录的 `data/investments.db`。

## 启动

1. 安装 Python 3.10 或更高版本，并确认命令行中的 `python --version` 可用。
2. 在 Windows 中双击项目根目录的 `run_investment.bat`。它会启动服务并自动打开浏览器。运行期间请保留命令行窗口；关闭窗口即停止服务。

也可以在项目根目录用 PowerShell 启动：

```powershell
python -m investment_tracker.server
```

然后打开 <http://127.0.0.1:8765>。若要自动打开浏览器，命令末尾添加 `--open`。停止时在命令行窗口按 `Ctrl+C`。

首次使用时设置初始总资产及开始时间；剩余资金自动计入余额宝。之后可添加标的、记录买卖、追加总资产、编辑交易流水。“收益曲线”中，总资产图的节点显示当时资产总值与累计收益；单标的上图显示持仓数量的买卖阶梯变化，下图显示累计、已实现和浮动盈亏。悬停买卖节点可查看数量、单价、金额、交易后持仓及收益明细。

## 数据与导出

账本位于 `data/investments.db`。备份时先停止服务，再复制该文件。页面“交易流水”可导出 CSV 或 Excel；Excel 导出需要安装 `openpyxl`：

```powershell
python -m pip install "openpyxl>=3.1"
```

行情依赖公开网络接口，可能延迟或暂时不可用；页面也支持手动填写价格。更多计算规则和标的说明见 [INVESTMENT_README.md](INVESTMENT_README.md)。

如果端口 8765 已被占用，可在 PowerShell 中指定其他端口：

```powershell
$env:INVESTMENT_PORT = "8766"
python -m investment_tracker.server
```

此时访问 <http://127.0.0.1:8766>。
