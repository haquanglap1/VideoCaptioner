"""Qt fixtures for UI component tests.

Widgets are constructed but never shown. On CI ``QT_QPA_PLATFORM=offscreen`` is
set by the workflow; locally the native platform is fine.
"""

import sys

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
