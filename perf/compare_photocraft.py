"""Reproducible CPU/Qt hot-path measurements; no application window or user files."""
import argparse
import inspect
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cv2
import numpy as np
import PySide6
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from core import qt_image
from service import history_service, preprocessing_service, editing_service
from tools.patch_tools import PatchTool


def measure(fn, repeats=5):
    """Warm once, then report independent wall-clock samples in milliseconds."""
    fn()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - start) * 1000)
        del result
    return {"median_ms": statistics.median(samples), "samples_ms": samples}


def main():
    """Measure actual service functions at fixed sizes and preserve raw results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--baseline-qt-compat", action="store_true")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    if args.baseline_qt_compat:
        # Original PyQt-style setsize raises on PySide6. Remove only that call
        # in memory so baseline timings retain all original copies/algorithms.
        for module, name in [(qt_image, "qimage_to_bgr"), (history_service, "_rgba_view")]:
            source = inspect.getsource(getattr(module, name))
            source = "\n".join(line for line in source.splitlines() if "bits.setsize(" not in line)
            exec(source, module.__dict__)
    results = {"environment": {"python": sys.version, "platform": platform.platform(), "cpu": platform.processor(), "opencv": cv2.__version__, "opencv_threads": cv2.getNumThreads(), "numpy": np.__version__, "pyside": PySide6.__version__, "baseline_qt_compat": args.baseline_qt_compat}, "measurements": {}}
    rng = np.random.default_rng(42)
    for width, height in [(1024, 1024), (2048, 2048), (4000, 3000)]:
        array = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
        pixmap = qt_image.bgr_to_qpixmap(array)
        before = pixmap.toImage()
        after = before.copy()
        after.setPixelColor(100, 100, "red")
        options = preprocessing_service.PreprocessOptions(brightness_shift=12, contrast_shift=20)
        def preview():
            source = qt_image.qimage_to_bgr(pixmap)
            output, _ = preprocessing_service.apply_options(source, options)
            return qt_image.bgr_to_qpixmap(output)
        for name, fn in [("qt_to_bgr", lambda: qt_image.qimage_to_bgr(pixmap)), ("brightness", lambda: preprocessing_service.apply_options(array, options)), ("preview_chain", preview), ("history_one_pixel", lambda: history_service.changed_image_patch(before, after)), ("history_unchanged", lambda: history_service.changed_image_patch(before, QImage(before))), ("paint_short_stroke", lambda: editing_service.apply_paint_strokes(array, [((100, 100), (200, 100))], (20, 60, 90), 20, .5))]:
            results["measurements"][f"{width}x{height}/{name}"] = measure(fn)
    patch = rng.integers(0, 256, (768, 768, 3), dtype=np.uint8)
    mask = np.full((768, 768), 255, np.uint8)
    tool = PatchTool()
    tool.load_selection_patch(patch, mask, 100, 100)
    tool.state.placement_active = True
    tool.set_target_size(4000, 3000)
    tool.state.angle = 23
    def drag():
        tool.state.x_pos += 1
        p = tool.preview_payload()
        return qt_image.bgr_mask_to_qpixmap(p.patch, p.mask)
    results["measurements"]["768x768/patch_drag_payload"] = measure(drag)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({k: round(v["median_ms"], 3) for k, v in results["measurements"].items()}, indent=2))
    assert app is not None


if __name__ == "__main__":
    main()
