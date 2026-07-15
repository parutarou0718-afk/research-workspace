import json
import os
import subprocess
import sys

import pytest


PROBE = r"""
import json
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from research_workspace.presentation.main_window import MainWindow

app = QApplication([])
window = MainWindow(services=object())
window.resize(1180, 720)
window.show()
app.processEvents()
required = [*window.navigation_buttons.values()]
rectangles = [
    [widget.geometry().x(), widget.geometry().y(), widget.geometry().width(), widget.geometry().height()]
    for widget in required
]
print(json.dumps({
    "scale": window.devicePixelRatioF(),
    "minimum": [window.minimumWidth(), window.minimumHeight()],
    "visible": all(widget.isVisible() for widget in required),
    "fits": all(
        widget.sizeHint().width() <= widget.width() and widget.sizeHint().height() <= widget.height()
        for widget in [*window.findChildren(QLabel), *window.findChildren(QPushButton)]
        if widget.isVisible()
    ),
    "rectangles": rectangles,
}))
"""


def rectangles_overlap(left, right):
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    return lx < rx + rw and rx < lx + lw and ly < ry + rh and ry < ly + lh


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
def test_main_window_geometry_is_dpi_safe(scale):
    env = os.environ.copy()
    env.update({"QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": str(scale)})
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["scale"] == pytest.approx(scale)
    assert report["minimum"] == [1180, 720]
    assert report["visible"]
    assert report["fits"]
    assert not any(
        rectangles_overlap(left, right)
        for index, left in enumerate(report["rectangles"])
        for right in report["rectangles"][index + 1 :]
    )
