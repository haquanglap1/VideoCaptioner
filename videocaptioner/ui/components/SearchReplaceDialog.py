from typing import Optional

from PyQt5.QtWidgets import QWidget
from qfluentwidgets import BodyLabel, LineEdit, MessageBoxBase


class SearchReplaceDialog(MessageBoxBase):
    """搜索和替换对话框 (Hộp thoại tìm kiếm và thay thế)"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setup_ui()
        self.setWindowTitle(self.tr("Tìm kiếm và Thay thế"))

    def setup_ui(self) -> None:
        self.titleLabel = BodyLabel(self.tr("Tìm kiếm và Thay thế"), self)

        # 添加搜索文本输入框 (Ô tìm kiếm)
        self.search_edit = LineEdit(self)
        self.search_edit.setPlaceholderText(self.tr("Nhập từ tìm kiếm (Search for)"))
        self.search_edit.setClearButtonEnabled(True)

        # 添加替换文本输入框 (Ô thay thế)
        self.replace_edit = LineEdit(self)
        self.replace_edit.setPlaceholderText(self.tr("Nhập từ thay thế (Replace with)"))
        self.replace_edit.setClearButtonEnabled(True)

        self.search_edit.setMinimumWidth(300)
        self.replace_edit.setMinimumWidth(300)

        # 添加到布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.search_edit)
        self.viewLayout.addWidget(self.replace_edit)
        self.viewLayout.setSpacing(15)

        # 设置按钮文本
        self.yesButton.setText(self.tr("Thay thế"))
        self.cancelButton.setText(self.tr("Hủy"))

    def get_search_word(self) -> str:
        return self.search_edit.text()

    def get_replace_word(self) -> str:
        return self.replace_edit.text()
