"""Visual summaries of completed dataset generation runs."""
import os
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot, QUrl, QRectF
from PySide6.QtGui import QColor, QDesktopServices, QImageReader, QPainter, QFont, QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget


def open_result_folder(parent, path):
    """Open the actual absolute run directory and report OS errors instead of ignoring them."""
    root = Path(path).resolve() if path else None
    if root is None or not root.is_dir():
        QMessageBox.warning(parent, "결과 폴더", "결과 폴더가 없습니다. 저장 위치를 확인하세요.")
        return False
    try:
        if os.name == "nt":
            os.startfile(str(root))
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(root))):
            raise OSError("파일 관리자를 실행하지 못했습니다.")
    except OSError as error:
        QMessageBox.warning(parent, "결과 폴더 열기 실패", f"{root}\n\n{error}")
        return False
    return True


class _DistributionChart(QWidget):
    """Show six classes per page and the dataset split without a scrolling surface."""
    def __init__(self, parent):
        super().__init__(parent)
        self.names, self.counts, self.splits, self.page = [], {}, {}, 0
        self.setMinimumSize(220, 320)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = self.palette().windowText().color()
        muted = QColor(text_color)
        muted.setAlpha(170)
        track = QColor(text_color)
        track.setAlpha(38)
        font = self.font()
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(12, 24, f"클래스 분포 · {len(self.names)}개")
        start = self.page * 6
        available = max(90, self.height() - 140)
        columns = 2 if self.width() >= 320 else 1
        rows = max(1, (min(6, len(self.names) - start) + columns - 1) // columns)
        step = min(46, available / rows)
        peak = max(self.counts.values(), default=1) or 1
        width = (self.width() - 24 - (columns - 1) * 20) / columns
        for row, class_id in enumerate(range(start, min(start + 6, len(self.names)))):
            x = 12 + (row % columns) * (width + 20)
            y = 40 + (row // columns) * step
            count = self.counts.get(class_id, 0)
            painter.setPen(text_color)
            name = painter.fontMetrics().elidedText(f"{class_id}  {self.names[class_id]}", Qt.TextElideMode.ElideRight, int(width - 60))
            painter.drawText(QRectF(x, y, width - 60, 20), Qt.AlignmentFlag.AlignVCenter, name)
            painter.drawText(QRectF(x, y, width, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{count:,}")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track)
            painter.drawRoundedRect(QRectF(x, y + 23, width, 7), 3, 3)
            painter.setBrush(QColor.fromHsv((class_id * 67 + 205) % 360, 155, 210))
            painter.drawRoundedRect(QRectF(x, y + 23, width * count / peak, 7), 3, 3)
        if not self.names:
            painter.setPen(muted)
            painter.drawText(12, 60, "생성 후 분포가 표시됩니다.")
        width = self.width() - 24
        y = self.height() - 66
        painter.setPen(text_color)
        painter.drawText(12, y, "데이터 분할")
        total = sum(self.splits.values()) or 1
        x = 12.0
        colors = (QColor("#3585d5"), QColor("#2cb7a7"), QColor("#c79b40"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(12, y + 10, width, 10), 3, 3)
        for split, color in zip(("train", "val", "test"), colors):
            part = width * self.splits.get(split, 0) / total
            painter.setBrush(color)
            painter.drawRect(QRectF(x, y + 10, part, 10))
            x += part
        painter.setPen(muted)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(12, y + 42, f"Train {self.splits.get('train', 0)}   Val {self.splits.get('val', 0)}   Test {self.splits.get('test', 0)}")


class _PreviewSignals(QObject):
    loaded = Signal(int, object)


class _PreviewLoad(QRunnable):
    """Decode at most four representative output images off the UI thread."""
    def __init__(self, token, paths):
        super().__init__()
        self.token, self.paths = token, paths
        self.signals = _PreviewSignals()

    def run(self):
        images = []
        for path in self.paths:
            reader = QImageReader(str(path))
            size = reader.size()
            if size.width() > 640 or size.height() > 640:
                size.scale(640, 640, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(size)
            images.append(reader.read())
        self.signals.loaded.emit(self.token, images)


class _ResultPreview(QWidget):
    """Display a representative image without file navigation or editing controls."""
    def __init__(self, parent):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.remaining = 0
        self.message = "생성 후 표시됩니다."
        self.setMinimumSize(100, 160)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#20242b"))
        if self.pixmap.isNull():
            painter.setPen(QColor("#ADB0B7"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
        else:
            size = self.pixmap.size()
            size.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2, size.width(), size.height())
            painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        if self.remaining:
            painter.fillRect(self.rect(), QColor(100, 100, 100, 175))
            painter.setPen(QColor("#ffffff"))
            text = f"… +{self.remaining:,}"
            font = self.font()
            font.setPixelSize(22)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            advance = painter.fontMetrics().horizontalAdvance(text)
            if advance > self.width() - 12:
                font.setPixelSize(max(9, int(22 * (self.width() - 12) / advance)))
                painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)


class DatasetResultSummary(QWidget):
    """Show actual output totals, representative images and class/split distributions."""
    def __init__(self, parent=None, *, compact=False):
        super().__init__(parent)
        self.result = {}
        self._token = 0
        self._tasks = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8 if compact else 12)
        self.summary = QLabel("증강 결과 요약", self)
        self.summary.setStyleSheet("font-size: 17px; font-weight: 600;")
        root.addWidget(self.summary)
        metrics = QHBoxLayout()
        self.metric_values, self.metric_titles = {}, {}
        for key, title in (("images", "최종 저장 이미지"), ("annotations", "라벨 객체"), ("poisson", "합성 생성 / 요청"), ("issues", "실패 / 건너뜀")):
            card = QFrame(self)
            card.setObjectName("resultMetric")
            layout = QVBoxLayout(card)
            margins = (8, 5, 8, 5) if compact else (14, 9, 14, 9)
            layout.setContentsMargins(*margins)
            layout.setSpacing(2)
            value, caption = QLabel("—", card), QLabel(title, card)
            value.setObjectName("metricNumber")
            if compact:
                value.setStyleSheet("font-size: 22px;")
                caption.setWordWrap(True)
            layout.addWidget(value)
            layout.addWidget(caption)
            metrics.addWidget(card, 1)
            self.metric_values[key], self.metric_titles[key] = value, caption
        root.addLayout(metrics)
        work = QVBoxLayout() if compact else QHBoxLayout()
        work.setSpacing(8 if compact else 20)
        examples = QVBoxLayout()
        self.examples_title = QLabel("대표 결과", self)
        examples.addWidget(self.examples_title)
        samples = QHBoxLayout()
        self.previews, self.preview_captions, self.preview_tiles = [], [], []
        for index in range(4):
            container = QWidget(self)
            tile = QVBoxLayout(container)
            tile.setContentsMargins(0, 0, 0, 0)
            preview = _ResultPreview(self)
            if compact:
                preview.setMinimumWidth(68)
                preview.setMinimumHeight(110)
                preview.setMaximumHeight(160)
            caption = QLabel(f"결과 예시 {index + 1}", self)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setWordWrap(compact)
            tile.addWidget(preview, 1)
            tile.addWidget(caption)
            samples.addWidget(container, 1)
            self.previews.append(preview)
            self.preview_captions.append(caption)
            self.preview_tiles.append(container)
        examples.addLayout(samples, 1)
        self.output_summary = QLabel("실행이 끝나면 실제 저장 결과를 표시합니다.", self)
        self.output_summary.setWordWrap(True)
        examples.addWidget(self.output_summary)
        work.addLayout(examples, 1)
        side = QVBoxLayout()
        self.chart = _DistributionChart(self)
        if compact:
            self.chart.setMinimumSize(320, 230)
        else:
            self.chart.setFixedWidth(280)
        side.addWidget(self.chart, 1)
        self.class_navigation = QWidget(self)
        pages = QHBoxLayout(self.class_navigation)
        pages.setContentsMargins(0, 0, 0, 0)
        self.previous_classes, self.next_classes = QToolButton(self), QToolButton(self)
        self.previous_classes.setText("‹")
        self.next_classes.setText("›")
        self.previous_classes.clicked.connect(lambda: self._change_class_page(-1))
        self.next_classes.clicked.connect(lambda: self._change_class_page(1))
        self.class_page_label = QLabel(self)
        pages.addWidget(self.previous_classes)
        pages.addWidget(self.class_page_label, 1)
        pages.addWidget(self.next_classes)
        side.addWidget(self.class_navigation)
        work.addLayout(side, 1 if compact else 0)
        root.addLayout(work, 1)
        footer = QHBoxLayout()
        self.status_note = QLabel("아직 실행 결과가 없습니다.", self)
        self.status_note.setWordWrap(True)
        footer.addWidget(self.status_note, 1)
        self.open_button = QPushButton("결과 폴더 열기", self)
        self.open_button.clicked.connect(self.open_folder)
        self.open_button.setEnabled(False)
        footer.addWidget(self.open_button)
        root.addLayout(footer)
        self._change_class_page(0)

    def _change_class_page(self, delta):
        last = max(0, (len(self.chart.names) - 1) // 6)
        self.chart.page = max(0, min(last, self.chart.page + delta))
        self.previous_classes.setEnabled(self.chart.page > 0)
        self.next_classes.setEnabled(self.chart.page < last)
        self.class_page_label.setText(f"클래스 {self.chart.page + 1} / {last + 1}")
        self.class_navigation.setVisible(last > 0)
        self.chart.update()

    def set_result(self, result):
        """Summarize the completed run; never expose an input or output file browser."""
        self.result = result
        self._token += 1
        is_export = result.get("kind") == "export"
        state = {"complete": "완료", "partial": "일부 완료", "interrupted": "중단됨", "running": "실행 중"}.get(result.get("status"), "결과")
        self.summary.setText(f"{'내보내기' if is_export else '증강'} 결과 요약 · {state}")
        self.metric_values["images"].setText(f"{result.get('images', 0):,}")
        self.metric_values["annotations"].setText(f"{result.get('annotations', 0):,}")
        self.metric_titles["poisson"].setText("클래스" if is_export else "합성 생성 / 요청")
        self.metric_values["poisson"].setText(str(len(result.get("class_names", []))) if is_export else f"{result.get('poisson_samples', 0):,} / {result.get('requested_poisson', 0):,}")
        self.metric_values["issues"].setText(f"{result.get('failed', 0):,} / {result.get('skipped', 0):,}")
        self.chart.names = result.get("class_names", [])
        self.chart.counts = {int(key): value for key, value in result.get("class_distribution", {}).items()}
        self.chart.splits, self.chart.page = result.get("split_images", {}), 0
        self._change_class_page(0)
        entries = result.get("entries", [])
        composites = [entry for entry in entries if entry["kind"] == "poisson"]
        self.output_summary.setText(f"원본 기반 출력 {len(entries) - len(composites):,}장 · 합성 기반 출력 {len(composites):,}장")
        self.output_summary.setVisible(bool(entries))
        self.examples_title.setText("대표 합성 결과" if composites else "대표 출력 결과")
        candidates = composites or entries
        selected = [candidates[index] for index in sorted({round(index * (len(candidates) - 1) / 3) for index in range(4)})] if candidates else []
        paths = []
        root = Path(result["output_root"]).resolve() if result.get("output_root") else None
        for index, (preview, caption) in enumerate(zip(self.previews, self.preview_captions)):
            self.preview_tiles[index].setVisible(index < max(1, len(selected)))
            preview.pixmap = QPixmap()
            preview.remaining = max(0, len(candidates) - 3) if index == 3 else 0
            preview.message = "불러오는 중…" if index < len(selected) else "저장된 결과 이미지가 없습니다."
            caption.setText("나머지 결과" if preview.remaining else f"{'합성' if composites else '출력'} 예시 {index + 1}")
            preview.setToolTip(f"총 {len(candidates):,}장 중 나머지 {preview.remaining:,}장 (이 이미지 포함)" if preview.remaining else "")
            preview.update()
            if root and index < len(selected):
                path = (root / selected[index]["image"]).resolve()
                paths.append(path if path.is_relative_to(root) else root)
        if paths:
            task = _PreviewLoad(self._token, paths)
            task.signals.loaded.connect(self._loaded)
            self._tasks[self._token] = task
            QThreadPool.globalInstance().start(task)
        self.open_button.setEnabled(root is not None)
        self.status_note.setText("생성되지 않은 결과가 있습니다. 실패·건너뜀 수량을 확인하세요." if state in ("일부 완료", "중단됨") else "실제 저장된 결과를 기준으로 집계했습니다.")

    @Slot(int, object)
    def _loaded(self, token, images):
        self._tasks.pop(token, None)
        if token != self._token:
            return
        for preview, image in zip(self.previews, images):
            preview.pixmap = QPixmap.fromImage(image)
            preview.message = "미리보기를 표시할 수 없습니다."
            preview.update()

    def open_folder(self):
        return open_result_folder(self, self.result.get("output_root"))


class DatasetResultDialog(QDialog):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.setWindowTitle("데이터셋 결과 요약")
        self.resize(1120, 740)
        self.setMinimumSize(960, 640)
        layout = QVBoxLayout(self)
        self.summary = DatasetResultSummary(self)
        layout.addWidget(self.summary)
        self.summary.set_result(result)
