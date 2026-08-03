# BX_UI.py
# BevelX Maya UI.
#
# Qt/PySide UI only.
# Geometry work belongs in BX_core / BX_build.
#
# Maya 2023 uses PySide2.
# The fallback to PySide6 is here for future Maya versions / testing.

from __future__ import print_function

try:
    from PySide2 import QtWidgets, QtCore
    from shiboken2 import wrapInstance
except ImportError:
    from PySide6 import QtWidgets, QtCore
    from shiboken6 import wrapInstance

import maya.OpenMayaUI as omui

from BX_core import BX_settings
from BX_core import BX_core
from BX_core import BX_session


WINDOW_OBJECT_NAME = "BX_BevelX_Window"
_WINDOW_INSTANCE = None


# -----------------------------------------------------------------------------
# Maya Qt helpers
# -----------------------------------------------------------------------------

def maya_main_window():
    """
    Return Maya's main window as a QWidget.
    """

    ptr = omui.MQtUtil.mainWindow()

    if ptr is None:
        return None

    return wrapInstance(int(ptr), QtWidgets.QWidget)


def close_existing_window():
    """
    Close any existing BevelX Qt window.
    """

    app = QtWidgets.QApplication.instance()

    if app is None:
        return

    for widget in app.topLevelWidgets():
        if widget.objectName() == WINDOW_OBJECT_NAME:
            widget.close()
            widget.deleteLater()


# -----------------------------------------------------------------------------
# Main UI
# -----------------------------------------------------------------------------

class BevelXUI(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(BevelXUI, self).__init__(parent or maya_main_window())

        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("BevelX  ({0})".format(BX_settings.VERSION))
        self.setMinimumWidth(390)

        self._is_updating_preview = False
        self._width_slider_steps = 10000
        self._width_slider_max = 1.0
        self._syncing_width_widgets = False

        self._preview_timer = QtCore.QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self.update_preview)

        self._build_ui()
        self._connect_live_update_signals()
        self._load_defaults()

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        main_layout.addWidget(self._build_header_group())
        main_layout.addWidget(self._build_affect_group())
        main_layout.addWidget(self._build_width_group())
        main_layout.addWidget(self._build_geometry_group())
        main_layout.addWidget(self._build_profile_group())
        main_layout.addWidget(self._build_miter_group())
        main_layout.addWidget(self._build_options_group())
        main_layout.addLayout(self._build_action_buttons())

        main_layout.addStretch()

    def _build_header_group(self):
        group = QtWidgets.QGroupBox("BevelX")
        layout = QtWidgets.QVBoxLayout(group)

        label_a = QtWidgets.QLabel("Bx prototype: Qt UI -> settings -> core callbacks")
        label_b = QtWidgets.QLabel("No Maya polyBevel calls. Backend is ours.")

        layout.addWidget(label_a)
        layout.addWidget(label_b)

        return group

    def _build_affect_group(self):
        group = QtWidgets.QGroupBox("Affect")
        layout = QtWidgets.QHBoxLayout(group)

        self.affect_edges_radio = QtWidgets.QRadioButton("Edges")
        self.affect_vertices_radio = QtWidgets.QRadioButton("Vertices")

        self.affect_edges_radio.setChecked(True)

        layout.addWidget(self.affect_edges_radio)
        layout.addWidget(self.affect_vertices_radio)
        layout.addStretch()

        return group

    def _build_width_group(self):
        group = QtWidgets.QGroupBox("Width")
        layout = QtWidgets.QFormLayout(group)

        self.width_type_combo = QtWidgets.QComboBox()
        self.width_type_combo.addItems([
            "Offset",
            "Width",
            "Depth",
            "Percent",
            "Absolute",
        ])

        width_widget = QtWidgets.QWidget()
        width_layout = QtWidgets.QHBoxLayout(width_widget)
        width_layout.setContentsMargins(0, 0, 0, 0)
        width_layout.setSpacing(6)

        self.width_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.width_slider.setMinimum(0)
        self.width_slider.setMaximum(10000)

        self.width_spin = QtWidgets.QDoubleSpinBox()
        self.width_spin.setDecimals(4)
        self.width_spin.setMinimum(0.0)
        self.width_spin.setMaximum(100000.0)
        self.width_spin.setSingleStep(0.01)
        self.width_spin.setMinimumWidth(90)

        self.width_slider.setToolTip("Adaptive range. Type a larger width to expand slider max.")
        self.width_spin.setToolTip("Bevel width. Values above current slider max expand slider range.")

        width_layout.addWidget(self.width_slider)
        width_layout.addWidget(self.width_spin)

        layout.addRow("Width Type", self.width_type_combo)
        layout.addRow("Width", width_widget)

        return group

    def _nice_width_slider_max(self, width):
        """
        Return an adaptive slider maximum for the current width.

        Rule:
            - Always at least 1.0.
            - If user enters 55, slider max becomes 55.
            - If user enters 0.1, slider max can stay at 1.0.
            - If user enters bigger than current max, expand.
            - Do not shrink aggressively while dragging.
        """

        width = max(0.0, float(width))

        if width <= 1.0:
            return 1.0

        return width


    def _ensure_width_slider_can_represent(self, width):
        """
        Expand slider max if needed so the numeric value fits.
        """

        width = max(0.0, float(width))

        if width > self._width_slider_max:
            self._width_slider_max = self._nice_width_slider_max(width)


    def _width_to_slider_value(self, width):
        """
        Convert width float to slider integer using adaptive max.
        """

        width = max(0.0, float(width))

        self._ensure_width_slider_can_represent(width)

        if self._width_slider_max <= 0.0:
            return 0

        ratio = width / self._width_slider_max
        ratio = max(0.0, min(ratio, 1.0))

        return int(round(ratio * float(self._width_slider_steps)))


    def _slider_value_to_width(self, slider_value):
        """
        Convert slider integer to width float using adaptive max.
        """

        slider_value = max(0, min(int(slider_value), self._width_slider_steps))

        ratio = float(slider_value) / float(self._width_slider_steps)

        return ratio * self._width_slider_max


    def _set_width_value(self, width, expand_slider=True):
        """
        Set spinbox and slider without recursive signal spam.
        """

        width = max(0.0, float(width))

        if expand_slider:
            self._ensure_width_slider_can_represent(width)

        self._syncing_width_widgets = True

        try:
            spin_blocker = QtCore.QSignalBlocker(self.width_spin)
            slider_blocker = QtCore.QSignalBlocker(self.width_slider)

            self.width_spin.setValue(width)
            self.width_slider.setValue(self._width_to_slider_value(width))

            del spin_blocker
            del slider_blocker

        finally:
            self._syncing_width_widgets = False

    def _build_geometry_group(self):
        group = QtWidgets.QGroupBox("Geometry")
        layout = QtWidgets.QFormLayout(group)

        self.segments_spin = QtWidgets.QSpinBox()
        self.segments_spin.setMinimum(1)
        self.segments_spin.setMaximum(256)

        layout.addRow("Segments", self.segments_spin)

        return group

    def _build_profile_group(self):
        group = QtWidgets.QGroupBox("Profile")
        layout = QtWidgets.QFormLayout(group)

        self.profile_type_combo = QtWidgets.QComboBox()
        self.profile_type_combo.addItems([
            "Superellipse",
            "Custom",
        ])

        self.profile_shape_spin = QtWidgets.QDoubleSpinBox()
        self.profile_shape_spin.setDecimals(4)
        self.profile_shape_spin.setMinimum(0.0)
        self.profile_shape_spin.setMaximum(1.0)
        self.profile_shape_spin.setSingleStep(0.01)

        self.profile_preset_combo = QtWidgets.QComboBox()
        self.profile_preset_combo.addItems([
            "Default",
            "Support Loops",
            "Steps",
            "Cornice Molding",
            "Crown Molding",
        ])

        self.edit_custom_profile_button = QtWidgets.QPushButton("Edit Custom Profile")
        self.edit_custom_profile_button.clicked.connect(
            lambda: self._not_implemented("Custom profile editor")
        )

        layout.addRow("Profile Type", self.profile_type_combo)
        layout.addRow("Profile Shape", self.profile_shape_spin)
        layout.addRow("Preset", self.profile_preset_combo)
        layout.addRow("", self.edit_custom_profile_button)

        return group

    def _build_miter_group(self):
        group = QtWidgets.QGroupBox("Miter")
        layout = QtWidgets.QFormLayout(group)

        self.miter_outer_combo = QtWidgets.QComboBox()
        self.miter_outer_combo.addItems([
            "Sharp",
            "Patch",
            "Arc",
        ])

        self.miter_inner_combo = QtWidgets.QComboBox()
        self.miter_inner_combo.addItems([
            "Sharp",
            "Patch",
            "Arc",
        ])

        layout.addRow("Outer", self.miter_outer_combo)
        layout.addRow("Inner", self.miter_inner_combo)

        return group

    def _build_options_group(self):
        group = QtWidgets.QGroupBox("Options")
        layout = QtWidgets.QVBoxLayout(group)

        self.clamp_overlap_check = QtWidgets.QCheckBox("Clamp Overlap")
        self.loop_slide_check = QtWidgets.QCheckBox("Loop Slide")
        self.harden_normals_check = QtWidgets.QCheckBox("Harden Normals")
        self.mark_sharp_check = QtWidgets.QCheckBox("Mark Sharp")
        self.mark_seam_check = QtWidgets.QCheckBox("Mark Seam")
        self.debug_draw_check = QtWidgets.QCheckBox("Debug Draw")
        self.live_preview_check = QtWidgets.QCheckBox("Live Preview")

        self.material_index_spin = QtWidgets.QSpinBox()
        self.material_index_spin.setMinimum(-1)
        self.material_index_spin.setMaximum(100000)

        material_layout = QtWidgets.QFormLayout()
        material_layout.addRow("Material Index", self.material_index_spin)

        layout.addWidget(self.clamp_overlap_check)
        layout.addWidget(self.loop_slide_check)
        layout.addWidget(self.harden_normals_check)
        layout.addWidget(self.mark_sharp_check)
        layout.addWidget(self.mark_seam_check)
        layout.addLayout(material_layout)
        layout.addWidget(self.debug_draw_check)
        layout.addWidget(self.live_preview_check)

        return group

    def _build_action_buttons(self):
        layout = QtWidgets.QHBoxLayout()

        self.preview_button = QtWidgets.QPushButton("Preview")
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.reset_button = QtWidgets.QPushButton("Reset")

        self.preview_button.setMinimumHeight(34)
        self.apply_button.setMinimumHeight(34)
        self.reset_button.setMinimumHeight(34)

        self.preview_button.clicked.connect(self.preview)
        self.apply_button.clicked.connect(self.apply)
        self.reset_button.clicked.connect(self.reset)

        layout.addWidget(self.preview_button)
        layout.addWidget(self.apply_button)
        layout.addWidget(self.reset_button)

        return layout

    # -------------------------------------------------------------------------
    # Defaults / settings
    # -------------------------------------------------------------------------

    def _load_defaults(self):
        settings = BX_settings.copy_defaults()

        self.affect_edges_radio.setChecked(settings["affect"] == BX_settings.AFFECT_EDGES)
        self.affect_vertices_radio.setChecked(settings["affect"] == BX_settings.AFFECT_VERTICES)

        self._set_combo_by_constant(
            self.width_type_combo,
            settings["width_type"],
            {
                BX_settings.WIDTH_OFFSET: "Offset",
                BX_settings.WIDTH_WIDTH: "Width",
                BX_settings.WIDTH_DEPTH: "Depth",
                BX_settings.WIDTH_PERCENT: "Percent",
                BX_settings.WIDTH_ABSOLUTE: "Absolute",
            }
        )

        self._set_width_value(float(settings["width"]))
        self.segments_spin.setValue(int(settings["segments"]))

        self._set_combo_by_constant(
            self.profile_type_combo,
            settings["profile_type"],
            {
                BX_settings.PROFILE_SUPERELLIPSE: "Superellipse",
                BX_settings.PROFILE_CUSTOM: "Custom",
            }
        )

        self.profile_shape_spin.setValue(float(settings["profile_shape"]))
        self.profile_preset_combo.setCurrentText(settings["profile_preset"])

        self._set_combo_by_constant(
            self.miter_outer_combo,
            settings["miter_outer"],
            {
                BX_settings.MITER_SHARP: "Sharp",
                BX_settings.MITER_PATCH: "Patch",
                BX_settings.MITER_ARC: "Arc",
            }
        )

        self._set_combo_by_constant(
            self.miter_inner_combo,
            settings["miter_inner"],
            {
                BX_settings.MITER_SHARP: "Sharp",
                BX_settings.MITER_PATCH: "Patch",
                BX_settings.MITER_ARC: "Arc",
            }
        )

        self.clamp_overlap_check.setChecked(bool(settings["clamp_overlap"]))
        self.loop_slide_check.setChecked(bool(settings["loop_slide"]))
        self.harden_normals_check.setChecked(bool(settings["harden_normals"]))
        self.mark_sharp_check.setChecked(bool(settings["mark_sharp"]))
        self.mark_seam_check.setChecked(bool(settings["mark_seam"]))
        self.material_index_spin.setValue(int(settings["material_index"]))
        self.debug_draw_check.setChecked(bool(settings["debug_draw"]))

        # Off by default until I'm happy with script editor noise/performance.
        self.live_preview_check.setChecked(True)

    def collect_settings(self):
        """
        Collect settings from the BevelX Qt UI.

        Returns:
            Dictionary matching BX_settings.DEFAULT_SETTINGS keys.
        """

        settings = BX_settings.copy_defaults()

        settings["affect"] = (
            BX_settings.AFFECT_EDGES
            if self.affect_edges_radio.isChecked()
            else BX_settings.AFFECT_VERTICES
        )

        settings["width_type"] = self._label_to_constant(
            self.width_type_combo.currentText(),
            {
                "Offset": BX_settings.WIDTH_OFFSET,
                "Width": BX_settings.WIDTH_WIDTH,
                "Depth": BX_settings.WIDTH_DEPTH,
                "Percent": BX_settings.WIDTH_PERCENT,
                "Absolute": BX_settings.WIDTH_ABSOLUTE,
            }
        )

        settings["width"] = float(self.width_spin.value())
        settings["segments"] = int(self.segments_spin.value())

        settings["profile_type"] = self._label_to_constant(
            self.profile_type_combo.currentText(),
            {
                "Superellipse": BX_settings.PROFILE_SUPERELLIPSE,
                "Custom": BX_settings.PROFILE_CUSTOM,
            }
        )

        settings["profile_shape"] = float(self.profile_shape_spin.value())
        settings["profile_preset"] = self.profile_preset_combo.currentText()

        settings["miter_outer"] = self._label_to_constant(
            self.miter_outer_combo.currentText(),
            {
                "Sharp": BX_settings.MITER_SHARP,
                "Patch": BX_settings.MITER_PATCH,
                "Arc": BX_settings.MITER_ARC,
            }
        )

        settings["miter_inner"] = self._label_to_constant(
            self.miter_inner_combo.currentText(),
            {
                "Sharp": BX_settings.MITER_SHARP,
                "Patch": BX_settings.MITER_PATCH,
                "Arc": BX_settings.MITER_ARC,
            }
        )

        settings["clamp_overlap"] = self.clamp_overlap_check.isChecked()
        settings["loop_slide"] = self.loop_slide_check.isChecked()
        settings["harden_normals"] = self.harden_normals_check.isChecked()
        settings["mark_sharp"] = self.mark_sharp_check.isChecked()
        settings["mark_seam"] = self.mark_seam_check.isChecked()
        settings["material_index"] = int(self.material_index_spin.value())
        settings["debug_draw"] = self.debug_draw_check.isChecked()

        return settings

    # -------------------------------------------------------------------------
    # Live update
    # -------------------------------------------------------------------------

    def _connect_live_update_signals(self):
        """
        Connect controls that should rebuild preview.

        For now width is the main live signal.
        """

        self.width_spin.valueChanged.connect(self.on_width_spin_changed)
        self.width_slider.valueChanged.connect(self.on_width_slider_changed)

        self.width_type_combo.currentIndexChanged.connect(self.schedule_update_preview)
        self.debug_draw_check.stateChanged.connect(self.schedule_update_preview)

    def on_width_spin_changed(self, value):
        """
        Numeric width changed.

        If the user types a value larger than the current slider range,
        expand the slider range to that value.

        Example:
            User enters 55
            slider represents 0..55
            slider handle moves to max
        """

        if self._syncing_width_widgets:
            return

        value = max(0.0, float(value))

        self._syncing_width_widgets = True

        try:
            self._ensure_width_slider_can_represent(value)

            slider_blocker = QtCore.QSignalBlocker(self.width_slider)
            self.width_slider.setValue(self._width_to_slider_value(value))
            del slider_blocker

        finally:
            self._syncing_width_widgets = False

        self.schedule_update_preview()


    def on_width_slider_changed(self, value):
        """
        Slider width changed.

        Slider maps from:
            0..10000
        to:
            0..self._width_slider_max

        If numeric field was previously set to 55, slider max remains 55.
        """

        if self._syncing_width_widgets:
            return

        width = self._slider_value_to_width(value)

        self._syncing_width_widgets = True

        try:
            spin_blocker = QtCore.QSignalBlocker(self.width_spin)
            self.width_spin.setValue(width)
            del spin_blocker

        finally:
            self._syncing_width_widgets = False

        self.schedule_update_preview()


    def schedule_update_preview(self, *args):
        """
        Debounced live preview request.

        This avoids rebuilding preview on every tiny spinbox internal event.
        """

        if not self.live_preview_check.isChecked():
            return

        session = BX_session.get_current_session()

        if not session.active:
            return

        self._preview_timer.start()

    def update_preview(self):
        """
        Rebuild active preview from current settings.

        Does not apply geometry.
        """

        if self._is_updating_preview:
            return

        self._is_updating_preview = True

        try:
            settings = self.collect_settings()
            BX_core.update_preview(settings)

        except Exception as exc:
            print("[BevelX] Live preview update failed: {0}".format(exc))

        finally:
            self._is_updating_preview = False

    # -------------------------------------------------------------------------
    # Button callbacks
    # -------------------------------------------------------------------------

    def preview(self):
        settings = self.collect_settings()
        BX_core.preview(settings)

        # Make sure live updates happen after the first preview.
        self.live_preview_check.setChecked(True)

    def apply(self):
        settings = self.collect_settings()
        BX_core.apply(settings)

    def reset(self):
        BX_core.reset()
        self._load_defaults()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _label_to_constant(label, mapping):
        return mapping.get(label, label.upper().replace(" ", "_"))

    @staticmethod
    def _set_combo_by_constant(combo, value, mapping):
        label = mapping.get(value)

        if label is None:
            return

        index = combo.findText(label)

        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _not_implemented(feature_name):
        QtWidgets.QMessageBox.information(
            None,
            "BevelX",
            "BevelX: {0} is not implemented yet.".format(feature_name)
        )


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def show():
    """
    Show BevelX Qt window.

    A global reference is kept so Maya does not garbage collect the dialog.
    """

    global _WINDOW_INSTANCE

    close_existing_window()

    _WINDOW_INSTANCE = BevelXUI()
    _WINDOW_INSTANCE.show()
    _WINDOW_INSTANCE.raise_()
    _WINDOW_INSTANCE.activateWindow()

    return _WINDOW_INSTANCE


if __name__ == "__main__":
    show()