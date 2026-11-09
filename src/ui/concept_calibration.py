"""Guided calibration uses the same unified workspace as board setup."""

from . import tokens as T
from .concept_boards import draw


def draw_board_calibration(app, w, h):
    return draw(app, w - T.NAV_RAIL_W, h, offset_x=T.NAV_RAIL_W, guided=True)
