from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QImage,
    QImageReader,
    QPainter,
    QPixmap,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QColorDialog,
    QInputDialog,
)

from .settings import ExportSettings, Template, WatermarkSettings
from .template_manager import TemplateManager

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
OUTPUT_FORMATS = ["PNG", "JPEG"]


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def load_qimage(path: Path) -> QImage:
    reader = QImageReader(str(path))
    image = reader.read()
    return image


class ImageEntry:
    def __init__(self, path: Path, image: QImage) -> None:
        self.path = path
        self.image = image
        self.display_name = path.name
        self.pixmap = QPixmap.fromImage(image)
        self.thumbnail = QPixmap.fromImage(
            image.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    @property
    def size(self) -> Tuple[int, int]:
        return self.image.width(), self.image.height()


class ImageListWidget(QListWidget):
    filesDropped = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(96, 96))
        self.setResizeMode(QListWidget.Adjust)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    paths.append(url.toLocalFile())
            if paths:
                self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class WatermarkTextItem(QGraphicsTextItem):
    positionChanged = Signal(float, float)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFlag(QGraphicsTextItem.ItemIsMovable, True)
        self.setFlag(QGraphicsTextItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsTextItem.ItemSendsScenePositionChanges, True)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            scene_rect = self.scene().sceneRect()
            width = max(scene_rect.width(), 1)
            height = max(scene_rect.height(), 1)
            x_ratio = max(0.0, min(1.0, value.x() / width))
            y_ratio = max(0.0, min(1.0, value.y() / height))
            self.positionChanged.emit(x_ratio, y_ratio)
        return super().itemChange(change, value)


class PreviewView(QGraphicsView):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInViewIfNeeded()

    def fitInViewIfNeeded(self) -> None:
        scene = self.scene()
        if scene and not scene.sceneRect().isNull():
            self.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photo Watermark")
        self.resize(1200, 800)

        self.template_manager = TemplateManager()
        last_settings = self.template_manager.get_last_settings()
        self.watermark_settings = last_settings.watermark
        self.export_settings = last_settings.export
        self.current_template_name = last_settings.name

        self.image_entries = []  # type: List[ImageEntry]
        self.current_index = -1

        self.scene = QGraphicsScene(self)
        self.pixmap_item = None
        self.watermark_item = WatermarkTextItem()
        self.watermark_item.setZValue(10)
        self.watermark_item.positionChanged.connect(self._on_manual_position_change)

        self.preview = PreviewView()
        self.preview.setScene(self.scene)
        self.scene.addItem(self.watermark_item)

        self.image_list = ImageListWidget()
        self.image_list.currentRowChanged.connect(self._on_image_selected)
        self.image_list.filesDropped.connect(self._handle_dropped_paths)

        controls_widget = self._build_controls()
        controls_area = QScrollArea()
        controls_area.setWidgetResizable(True)
        controls_area.setWidget(controls_widget)
        controls_area.setMinimumWidth(260)

        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_list.setMinimumWidth(220)

        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(10)
        main_layout.addWidget(self.image_list, 1)
        main_layout.addWidget(self.preview, 6)
        main_layout.addWidget(controls_area, 3)
        self.setCentralWidget(central)

        toolbar = QToolBar("File")
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)

        import_action = toolbar.addAction("导入图片")
        import_action.triggered.connect(self._trigger_file_import)
        folder_action = toolbar.addAction("导入文件夹")
        folder_action.triggered.connect(self._trigger_folder_import)
        export_action = toolbar.addAction("批量导出")
        export_action.triggered.connect(self._export_images)

        self._refresh_template_combo()
        self._update_controls_from_settings()

    # region UI Builders
    def _build_controls(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_watermark_box())
        layout.addWidget(self._build_position_box())
        layout.addWidget(self._build_export_box())
        layout.addWidget(self._build_template_box())
        layout.addStretch(1)
        return container

    def _build_watermark_box(self) -> QGroupBox:
        box = QGroupBox("文本水印")
        form = QFormLayout(box)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请输入水印内容")
        self.text_input.textChanged.connect(self._on_text_changed)
        form.addRow("内容", self.text_input)

        font_families = sorted(QFontDatabase().families())
        self.font_combo = QComboBox()
        self.font_combo.addItems(font_families)
        self.font_combo.currentTextChanged.connect(self._on_font_family_changed)
        form.addRow("字体", self.font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 200)
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        form.addRow("字号", self.font_size_spin)

        color_layout = QHBoxLayout()
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(32, 20)
        self.color_preview.setFrameShape(QLabel.Box)
        self.color_preview.setAutoFillBackground(True)
        color_button = QPushButton("选择颜色")
        color_button.clicked.connect(self._choose_color)
        color_layout.addWidget(self.color_preview)
        color_layout.addWidget(color_button)
        form.addRow("颜色", color_layout)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        form.addRow("透明度", self.opacity_slider)

        return box

    def _build_position_box(self) -> QGroupBox:
        box = QGroupBox("水印位置")
        layout = QVBoxLayout(box)

        grid_layout = QGridLayout()
        positions = [
            ("左上", 0, 0, 0.05, 0.05),
            ("上中", 0, 1, 0.5, 0.05),
            ("右上", 0, 2, 0.95, 0.05),
            ("左中", 1, 0, 0.05, 0.5),
            ("中心", 1, 1, 0.5, 0.5),
            ("右中", 1, 2, 0.95, 0.5),
            ("左下", 2, 0, 0.05, 0.95),
            ("下中", 2, 1, 0.5, 0.95),
            ("右下", 2, 2, 0.95, 0.95),
        ]

        for label, row, col, x_ratio, y_ratio in positions:
            button = QPushButton(label)
            button.clicked.connect(lambda _, x=x_ratio, y=y_ratio: self._set_watermark_position(x, y))
            grid_layout.addWidget(button, row, col)
        layout.addLayout(grid_layout)

        info_label = QLabel("提示：可直接在预览中拖动水印到任意位置。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        return box

    def _build_export_box(self) -> QGroupBox:
        box = QGroupBox("导出设置")
        form = QFormLayout(box)

        folder_layout = QHBoxLayout()
        self.output_folder_label = QLabel("未选择")
        self.output_folder_label.setFrameShape(QLabel.Panel)
        self.output_folder_label.setFrameShadow(QLabel.Sunken)
        select_btn = QPushButton("选择文件夹")
        select_btn.clicked.connect(self._choose_output_folder)
        folder_layout.addWidget(self.output_folder_label, 1)
        folder_layout.addWidget(select_btn)
        form.addRow("输出目录", folder_layout)

        self.format_combo = QComboBox()
        self.format_combo.addItems(OUTPUT_FORMATS)
        self.format_combo.currentTextChanged.connect(self._on_output_format_changed)
        form.addRow("输出格式", self.format_combo)

        naming_layout = QVBoxLayout()
        self.naming_group = QButtonGroup(self)
        self.naming_original = QRadioButton("保留原文件名")
        self.naming_prefix = QRadioButton("添加前缀")
        self.naming_suffix = QRadioButton("添加后缀")
        self.naming_group.addButton(self.naming_original)
        self.naming_group.addButton(self.naming_prefix)
        self.naming_group.addButton(self.naming_suffix)
        self.naming_original.toggled.connect(lambda checked: checked and self._on_naming_mode_changed("original"))
        self.naming_prefix.toggled.connect(lambda checked: checked and self._on_naming_mode_changed("prefix"))
        self.naming_suffix.toggled.connect(lambda checked: checked and self._on_naming_mode_changed("suffix"))
        naming_layout.addWidget(self.naming_original)
        naming_layout.addWidget(self.naming_prefix)
        naming_layout.addWidget(self.naming_suffix)
        form.addRow("命名规则", naming_layout)

        self.prefix_input = QLineEdit()
        self.prefix_input.textChanged.connect(self._on_prefix_changed)
        form.addRow("前缀", self.prefix_input)

        self.suffix_input = QLineEdit()
        self.suffix_input.textChanged.connect(self._on_suffix_changed)
        form.addRow("后缀", self.suffix_input)

        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(10, 100)
        self.quality_slider.valueChanged.connect(self._on_quality_changed)
        form.addRow("JPEG质量", self.quality_slider)

        export_btn = QPushButton("立即导出")
        export_btn.clicked.connect(self._export_images)
        form.addRow(export_btn)
        return box

    def _build_template_box(self) -> QGroupBox:
        box = QGroupBox("水印模板")
        layout = QVBoxLayout(box)

        self.template_combo = QComboBox()
        self.template_combo.currentTextChanged.connect(self._on_template_selected)
        layout.addWidget(self.template_combo)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存当前设置…")
        save_btn.clicked.connect(self._save_template)
        delete_btn = QPushButton("删除模板")
        delete_btn.clicked.connect(self._delete_template)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(delete_btn)
        layout.addLayout(btn_layout)

        return box

    # endregion

    # region Event handlers
    def _on_text_changed(self) -> None:
        self.watermark_settings.text = self.text_input.toPlainText()
        self._update_watermark_item()

    def _on_font_family_changed(self, family: str) -> None:
        self.watermark_settings.font_family = family
        self._update_watermark_item()

    def _on_font_size_changed(self, size: int) -> None:
        self.watermark_settings.font_size = size
        self._update_watermark_item()

    def _choose_color(self) -> None:
        current = QColor(self.watermark_settings.color)
        color = QColorDialog.getColor(current, self, "选择颜色")
        if color.isValid():
            self.watermark_settings.color = color.name(QColor.HexRgb)
            self._update_color_preview()
            self._update_watermark_item()

    def _on_opacity_changed(self, value: int) -> None:
        self.watermark_settings.opacity = value
        self._update_watermark_item()

    def _set_watermark_position(self, x_ratio: float, y_ratio: float) -> None:
        self.watermark_settings.position_ratio = (x_ratio, y_ratio)
        self._apply_watermark_position()

    def _on_manual_position_change(self, x_ratio: float, y_ratio: float) -> None:
        self.watermark_settings.position_ratio = (x_ratio, y_ratio)

    def _on_output_format_changed(self, fmt: str) -> None:
        self.export_settings.output_format = fmt

    def _on_naming_mode_changed(self, mode: str) -> None:
        self.export_settings.naming_mode = mode

    def _on_prefix_changed(self, text: str) -> None:
        self.export_settings.prefix = text

    def _on_suffix_changed(self, text: str) -> None:
        self.export_settings.suffix = text

    def _on_quality_changed(self, value: int) -> None:
        self.export_settings.jpeg_quality = value

    def closeEvent(self, event) -> None:
        self.template_manager.record_last_settings(
            self.watermark_settings, self.export_settings, self.current_template_name
        )
        super().closeEvent(event)

    def _on_image_selected(self, index: int) -> None:
        if 0 <= index < len(self.image_entries):
            self.current_index = index
            self._load_preview()

    def _handle_dropped_paths(self, path_strings: List[str]) -> None:
        paths = [Path(p) for p in path_strings]
        self._add_images(paths)

    # endregion

    # region Image management
    def _trigger_file_import(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            str(Path.home()),
            "图像文件 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if files:
            self._add_images([Path(f) for f in files])

    def _trigger_folder_import(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", str(Path.home()))
        if folder:
            folder_path = Path(folder)
            image_paths = [p for p in folder_path.rglob("*") if p.is_file() and is_supported_image(p)]
            if not image_paths:
                QMessageBox.information(self, "提示", "该文件夹中没有支持的图片格式。")
                return
            self._add_images(image_paths)

    def _add_images(self, paths: List[Path]) -> None:
        new_entries = []
        for path in paths:
            if path.is_dir():
                image_paths = [p for p in path.rglob("*") if p.is_file() and is_supported_image(p)]
                for img_path in image_paths:
                    self._try_add_image(img_path, new_entries)
            elif is_supported_image(path):
                self._try_add_image(path, new_entries)

        if not new_entries:
            QMessageBox.warning(self, "提示", "未找到可以导入的图片文件。")
            return

        for entry in new_entries:
            item = QListWidgetItem(entry.display_name)
            item.setIcon(QIcon(entry.thumbnail))
            self.image_list.addItem(item)
            self.image_entries.append(entry)

        if self.current_index == -1 and self.image_entries:
            self.image_list.setCurrentRow(0)

    def _try_add_image(self, path: Path, collection: List[ImageEntry]) -> None:
        if any(entry.path == path for entry in self.image_entries):
            return
        image = load_qimage(path)
        if image.isNull():
            return
        collection.append(ImageEntry(path, image))

    def _load_preview(self) -> None:
        if not (0 <= self.current_index < len(self.image_entries)):
            if self.pixmap_item is not None:
                self.scene.removeItem(self.pixmap_item)
                self.pixmap_item = None
            self.scene.setSceneRect(QRectF())
            return

        entry = self.image_entries[self.current_index]
        pixmap = entry.pixmap

        if self.pixmap_item is not None:
            self.scene.removeItem(self.pixmap_item)
            self.pixmap_item = None

        self.pixmap_item = self.scene.addPixmap(pixmap)
        if self.watermark_item.scene() is None:
            self.scene.addItem(self.watermark_item)
        elif self.watermark_item.scene() is not self.scene:
            self.watermark_item.scene().removeItem(self.watermark_item)
            self.scene.addItem(self.watermark_item)

        self.scene.setSceneRect(pixmap.rect())
        self.preview.fitInViewIfNeeded()
        self._update_watermark_item()

    # endregion

    # region Watermark preview
    def _update_watermark_item(self) -> None:
        font = QFont(self.watermark_settings.font_family, self.watermark_settings.font_size)
        self.watermark_item.setFont(font)
        self.watermark_item.setPlainText(self.watermark_settings.text)

        color = QColor(self.watermark_settings.color)
        color.setAlpha(int(255 * (self.watermark_settings.opacity / 100)))
        self.watermark_item.setDefaultTextColor(color)

        self._apply_watermark_position()
        self.preview.viewport().update()

    def _apply_watermark_position(self) -> None:
        if not self.scene.sceneRect().isNull():
            width = self.scene.sceneRect().width()
            height = self.scene.sceneRect().height()
            x_ratio, y_ratio = self.watermark_settings.position_ratio
            x = x_ratio * width
            y = y_ratio * height
            self.watermark_item.setPos(QPointF(x, y))

    def _update_color_preview(self) -> None:
        palette = self.color_preview.palette()
        palette.setColor(self.color_preview.backgroundRole(), QColor(self.watermark_settings.color))
        self.color_preview.setPalette(palette)

    # endregion

    # region Export
    def _choose_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹", str(Path.home()))
        if folder:
            self.export_settings.output_folder = folder
            self.output_folder_label.setText(folder)

    def _export_images(self) -> None:
        if not self.image_entries:
            QMessageBox.warning(self, "提示", "请先导入至少一张图片。")
            return
        if not self.export_settings.output_folder:
            QMessageBox.warning(self, "提示", "请先选择输出文件夹。")
            return

        output_folder = Path(self.export_settings.output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)

        for entry in self.image_entries:
            if Path(entry.path).parent.resolve() == output_folder.resolve():
                QMessageBox.warning(self, "提示", "输出文件夹不能与原图所在目录相同。")
                return

        failures = []
        for entry in self.image_entries:
            success = self._export_single(entry)
            if not success:
                failures.append(entry.display_name)

        if failures:
            QMessageBox.warning(
                self,
                "导出完成",
                "以下文件导出失败：\n" + "\n".join(failures),
            )
        else:
            QMessageBox.information(self, "导出完成", "所有图片导出成功。")

    def _export_single(self, entry: ImageEntry) -> bool:
        try:
            image = QImage(entry.image)
            painter = QPainter(image)
            painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)

            font = QFont(self.watermark_settings.font_family, self.watermark_settings.font_size)
            color = QColor(self.watermark_settings.color)
            color.setAlpha(int(255 * (self.watermark_settings.opacity / 100)))

            x_ratio, y_ratio = self.watermark_settings.position_ratio
            x = x_ratio * image.width()
            y = y_ratio * image.height()

            painter.save()
            painter.translate(x, y)

            doc = QTextDocument()
            doc.setDocumentMargin(0)
            doc.setDefaultFont(font)
            doc.setPlainText(self.watermark_settings.text)

            cursor = QTextCursor(doc)
            cursor.select(QTextCursor.Document)
            char_format = cursor.charFormat()
            char_format.setForeground(color)
            cursor.setCharFormat(char_format)

            text_option = QTextOption(Qt.AlignLeft | Qt.AlignTop)
            doc.setDefaultTextOption(text_option)
            doc.drawContents(painter)
            painter.restore()
            painter.end()

            output_name = self._build_output_name(entry.path.stem)
            output_ext = self.export_settings.output_format.lower()
            output_filename = "{}.{}".format(output_name, output_ext)
            output_path = Path(self.export_settings.output_folder) / output_filename

            quality = self.export_settings.jpeg_quality if output_ext == "jpeg" else -1
            image_format = "JPEG" if output_ext == "jpeg" else "PNG"
            if not image.save(str(output_path), image_format, quality):
                return False
            return True
        except Exception:
            return False

    def _build_output_name(self, original_stem: str) -> str:
        mode = self.export_settings.naming_mode
        if mode == "original":
            return original_stem
        if mode == "prefix":
            return "{}{}".format(self.export_settings.prefix, original_stem)
        if mode == "suffix":
            return "{}{}".format(original_stem, self.export_settings.suffix)
        return original_stem

    # endregion

    # region Templates
    def _refresh_template_combo(self) -> None:
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        templates = self.template_manager.list_templates()
        for tpl in templates:
            self.template_combo.addItem(tpl.name)
        last_name = self.template_manager.get_last_template_name()
        if last_name and last_name in [tpl.name for tpl in templates]:
            index = self.template_combo.findText(last_name)
            self.template_combo.setCurrentIndex(index)
        else:
            self.template_combo.setCurrentIndex(0 if templates else -1)
        self.template_combo.blockSignals(False)

    def _on_template_selected(self, name: str) -> None:
        template = self.template_manager.get_template(name)
        if not template:
            return
        self.current_template_name = template.name
        self.watermark_settings = template.watermark
        self.export_settings = template.export
        self._update_controls_from_settings()
        self._update_watermark_item()

    def _save_template(self) -> None:
        name, ok = QInputDialog.getText(self, "保存模板", "请输入模板名称：", text=self.current_template_name or "新模板")
        if not ok or not name.strip():
            return
        template = Template(name=name.strip(), watermark=self.watermark_settings, export=self.export_settings)
        self.template_manager.save_template(template)
        self.current_template_name = template.name
        self._refresh_template_combo()
        QMessageBox.information(self, "成功", "模板已保存。")

    def _delete_template(self) -> None:
        current_name = self.template_combo.currentText()
        if not current_name:
            return
        prompt = "确定要删除模板『{}』吗？".format(current_name)
        if QMessageBox.question(self, "确认", prompt) != QMessageBox.Yes:
            return
        success = self.template_manager.delete_template(current_name)
        if success:
            QMessageBox.information(self, "提示", "模板已删除。")
            self._refresh_template_combo()
        else:
            QMessageBox.warning(self, "提示", "删除失败，模板不存在。")

    # endregion

    # region Helpers
    def _update_controls_from_settings(self) -> None:
        self.text_input.blockSignals(True)
        self.text_input.setPlainText(self.watermark_settings.text)
        self.text_input.blockSignals(False)

        index = self.font_combo.findText(self.watermark_settings.font_family)
        if index == -1:
            self.font_combo.addItem(self.watermark_settings.font_family)
            index = self.font_combo.findText(self.watermark_settings.font_family)
        self.font_combo.blockSignals(True)
        self.font_combo.setCurrentIndex(index)
        self.font_combo.blockSignals(False)

        self.font_size_spin.blockSignals(True)
        self.font_size_spin.setValue(self.watermark_settings.font_size)
        self.font_size_spin.blockSignals(False)

        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(self.watermark_settings.opacity)
        self.opacity_slider.blockSignals(False)

        self._update_color_preview()

        self.format_combo.blockSignals(True)
        fmt_index = self.format_combo.findText(self.export_settings.output_format)
        if fmt_index != -1:
            self.format_combo.setCurrentIndex(fmt_index)
        self.format_combo.blockSignals(False)

        self.naming_original.setChecked(self.export_settings.naming_mode == "original")
        self.naming_prefix.setChecked(self.export_settings.naming_mode == "prefix")
        self.naming_suffix.setChecked(self.export_settings.naming_mode == "suffix")

        self.prefix_input.blockSignals(True)
        self.prefix_input.setText(self.export_settings.prefix)
        self.prefix_input.blockSignals(False)

        self.suffix_input.blockSignals(True)
        self.suffix_input.setText(self.export_settings.suffix)
        self.suffix_input.blockSignals(False)

        self.output_folder_label.setText(self.export_settings.output_folder or "未选择")

        self.quality_slider.blockSignals(True)
        self.quality_slider.setValue(self.export_settings.jpeg_quality)
        self.quality_slider.blockSignals(False)

    # endregion


def main() -> None:
    import sys

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
