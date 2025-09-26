#!/usr/bin/env python3
"""
DinoPit Studios Color Configuration
Centralized color scheme for the DinoPit Studios GUI application.
"""

from typing import TYPE_CHECKING

from .scaling import get_scaling_helper

if TYPE_CHECKING:
    from collections.abc import Callable


class DinoPitColors:
    """Color constants for DinoPit Studios branding."""

    # Primary Brand Colors
    DINOPIT_ORANGE = "#FF6B35"  # Main brand orange
    DINOPIT_FIRE = "#FF4500"  # Fire orange accent
    STUDIOS_CYAN = "#00BFFF"  # "STUDIOS" cyan blue

    # Background Colors
    MAIN_BACKGROUND = "#2B3A52"  # Desaturated blue main background
    PANEL_BACKGROUND = "#34435A"  # Blue-gray for panels
    SIDEBAR_BACKGROUND = "#344359"  # Slightly different for sidebars

    # UI Element Colors
    SOFT_ORANGE = "#CC8B66"  # Soft orange for borders
    SOFT_ORANGE_HOVER = "#E6A085"  # Hover state for soft orange

    # Text Colors
    PRIMARY_TEXT = "#FFFFFF"  # White text for headers
    SECONDARY_TEXT = "#CCCCCC"  # Light gray for secondary text
    ACCENT_TEXT = STUDIOS_CYAN  # Cyan for secondary text
    BRAND_TEXT = DINOPIT_ORANGE  # Orange for brand elements

    # Border and Accent Colors
    BORDER_COLOR = SOFT_ORANGE  # Default border color
    BORDER_HOVER = SOFT_ORANGE_HOVER  # Border hover state
    ACCENT_BORDER = DINOPIT_ORANGE  # Accent borders

    @classmethod
    def get_stylesheet(
        cls, element_type: str = "default", scale_factor: float | None = None
    ) -> str:
        """Get common stylesheets for different element types."""
        scaling = get_scaling_helper()
        _ = scale_factor  # reserved for future scaling support; avoids unused-argument warning

        # Dictionary-based lookup eliminates long if-elif chain
        stylesheets: dict[str, Callable[[], str]] = {
            "main_background": lambda: f"background-color: {cls.MAIN_BACKGROUND};",
            "header": lambda: f"""
                background-color: {cls.DINOPIT_ORANGE};
                border-bottom: {scaling.scaled_size(2)}px solid {cls.DINOPIT_FIRE};
                color: {cls.PRIMARY_TEXT};
                font-weight: bold;
                font-size: {scaling.scaled_font_size(14)}px;
            """,
            "panel": lambda: f"background-color: {cls.PANEL_BACKGROUND};",
            "input_field": lambda: f"""
                QLineEdit {{
                    border: {scaling.scaled_size(1)}px solid {cls.BORDER_COLOR};
                    border-radius: {scaling.scaled_size(20)}px;
                    padding: {scaling.scaled_size(8)}px {scaling.scaled_size(15)}px;
                    font-size: {scaling.scaled_font_size(14)}px;
                    background-color: {cls.MAIN_BACKGROUND};
                    color: {cls.ACCENT_TEXT};
                }}
                QLineEdit:focus {{
                    border-color: {cls.BORDER_HOVER};
                }}
            """,
            "button": lambda: f"""
                QPushButton {{
                    background-color: {cls.DINOPIT_ORANGE};
                    color: {cls.PRIMARY_TEXT};
                    border: none;
                    border-radius: {scaling.scaled_size(20)}px;
                    font-size: {scaling.scaled_font_size(16)}px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {cls.DINOPIT_FIRE};
                }}
                QPushButton:pressed {{
                    background-color: #E55A2B;
                }}
                QPushButton:disabled {{
                    background-color: #666666;
                    color: #999999;
                }}
            """,
        }

        # Use dictionary lookup with default fallback
        style_generator = stylesheets.get(element_type, lambda: "")
        return style_generator()
