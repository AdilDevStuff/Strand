"""Design system, color tokens, and stylesheets matching the sleek GitFiend dark interface."""

from __future__ import annotations

from typing import List


class Theme:
    """GitFiend modern dark theme design tokens."""
    # Backgrounds
    BG_PRIMARY = "#0e0f12"       # Deep dark window canvas
    BG_SIDEBAR = "#121316"       # Left sidebar background
    BG_SURFACE = "#16171b"       # Panes and card backgrounds
    BG_SURFACE_HOVER = "#1e2025" # Hover highlight
    BG_SURFACE_ACTIVE = "#252830"# Selected item background
    BG_INPUT = "#101114"         # Inputs and editors
    BG_CARD = "#15161a"          # Floating commit box / overlay cards

    # Borders
    BORDER_SUBTLE = "#1d1f24"
    BORDER_DEFAULT = "#25272e"
    BORDER_FOCUS = "#2563eb"

    # Typography
    TEXT_PRIMARY = "#f3f4f6"     # Crisp bright text
    TEXT_SECONDARY = "#9ca3af"   # Subtitle / author text
    TEXT_MUTED = "#6b7280"       # Timestamps and hashes

    # Status & Accent Colors
    ACCENT = "#2563eb"           # Vibrant primary blue
    ACCENT_HOVER = "#3b82f6"
    ACCENT_GLOW = "#1d4ed8"

    COLOR_ADDED = "#10b981"      # Emerald green
    COLOR_ADDED_BG = "#0d2b1f"
    COLOR_DELETED = "#ef4444"    # Rose red
    COLOR_DELETED_BG = "#311417"
    COLOR_MODIFIED = "#f59e0b"   # Amber
    COLOR_MODIFIED_BG = "#2a1c07"
    COLOR_UNTRACKED = "#9ca3af"
    COLOR_RENAMED = "#06b6d4"
    COLOR_CONFLICT = "#f97316"

    # macOS Titlebar Traffic Lights
    COLOR_TRAFFIC_RED = "#ff5f56"
    COLOR_TRAFFIC_YELLOW = "#ffbd2e"
    COLOR_TRAFFIC_GREEN = "#27c93f"

    # Commit Graph Branch Lane Colors (Cubic Bezier Tracks)
    LANE_PALETTE: List[str] = [
        "#06b6d4",  # cyan track
        "#f97316",  # orange track
        "#a855f7",  # purple track
        "#10b981",  # green track
        "#ec4899",  # pink track
        "#3b82f6",  # blue track
        "#eab308",  # yellow track
        "#14b8a6",  # teal track
    ]

    @classmethod
    def get_lane_color(cls, index: int) -> str:
        """Return the hex color string for a graph lane index."""
        return cls.LANE_PALETTE[index % len(cls.LANE_PALETTE)]

    @classmethod
    def main_stylesheet(cls) -> str:
        """Global Qt Stylesheet (QSS) for modern desktop application."""
        return f"""
        QWidget {{
            background-color: {cls.BG_PRIMARY};
            color: {cls.TEXT_PRIMARY};
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", Helvetica, Arial, sans-serif;
            font-size: 13px;
            selection-background-color: {cls.ACCENT};
            selection-color: #ffffff;
        }}

        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 7px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {cls.BORDER_DEFAULT};
            min-height: 20px;
            border-radius: 3px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {cls.TEXT_MUTED};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
            height: 0px;
        }}

        QScrollBar:horizontal {{
            border: none;
            background: transparent;
            height: 7px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {cls.BORDER_DEFAULT};
            min-width: 20px;
            border-radius: 3px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {cls.TEXT_MUTED};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            border: none;
            background: none;
            width: 0px;
        }}

        QPushButton {{
            background-color: {cls.BG_SURFACE};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_DEFAULT};
            border-radius: 6px;
            padding: 5px 12px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {cls.BG_SURFACE_HOVER};
            border-color: {cls.TEXT_MUTED};
        }}
        QPushButton:pressed {{
            background-color: {cls.BG_SURFACE_ACTIVE};
        }}
        QPushButton:disabled {{
            background-color: {cls.BG_PRIMARY};
            color: {cls.TEXT_MUTED};
            border-color: {cls.BORDER_SUBTLE};
        }}

        QPushButton#primaryButton {{
            background-color: {cls.ACCENT};
            color: #ffffff;
            border: 1px solid {cls.ACCENT};
            border-radius: 6px;
            font-weight: 600;
            padding: 8px 16px;
        }}
        QPushButton#primaryButton:hover {{
            background-color: {cls.ACCENT_HOVER};
            border-color: {cls.ACCENT_HOVER};
        }}
        QPushButton#primaryButton:pressed {{
            background-color: {cls.ACCENT_GLOW};
        }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {cls.BG_INPUT};
            color: {cls.TEXT_PRIMARY};
            border: 1px solid {cls.BORDER_DEFAULT};
            border-radius: 6px;
            padding: 6px 10px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {cls.BORDER_FOCUS};
        }}

        QCheckBox {{
            spacing: 8px;
            color: {cls.TEXT_PRIMARY};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {cls.BORDER_DEFAULT};
            border-radius: 4px;
            background-color: {cls.BG_INPUT};
        }}
        QCheckBox::indicator:hover {{
            border-color: {cls.ACCENT};
        }}
        QCheckBox::indicator:checked {{
            background-color: {cls.ACCENT};
            border-color: {cls.ACCENT};
            image: none;
        }}

        QSplitter::handle {{
            background-color: {cls.BORDER_SUBTLE};
        }}
        QSplitter::handle:hover {{
            background-color: {cls.ACCENT};
        }}
        """
