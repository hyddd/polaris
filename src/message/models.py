"""消息附件数据模型。"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class Attachment:
    """消息附件。"""

    type: Literal["image", "file"]
    data: str  # base64 编码的内容（图片）或文件路径（文件）
    mime_type: str  # "image/png", "application/pdf" 等
    filename: str = ""
