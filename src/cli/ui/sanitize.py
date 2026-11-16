"""终端输出过滤。模型输出、工具结果、会话内容都是不可信文本。

去掉 ANSI/OSC 等控制序列（改终端标题、写剪贴板、移动光标、伪造提示符等），
以及除换行和制表符以外的 C0/C1 控制字符。
"""
import re

_ESCAPES = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"     # OSC ... BEL / ST（终端标题、剪贴板、超链接）
    r"|\x1b[P^_X][^\x1b]*(?:\x1b\\)?"          # DCS / PM / APC / SOS
    r"|\x1b\[[0-?]*[ -/]*[@-~]"                # CSI（颜色、光标移动、清屏）
    r"|\x1b[ -/]*[0-~]"                        # 其余两字节 ESC 序列
    r"|\x9b[0-?]*[ -/]*[@-~]"                  # 8 位 CSI
    r"|[\x9d\x90\x9e\x9f][^\x07\x9c]*[\x07\x9c]?"  # 8 位 OSC/DCS/PM/APC
)
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def sanitize(text: str) -> str:
    text = text.replace("\r\n", "\n")
    return _CONTROLS.sub("", _ESCAPES.sub("", text))
