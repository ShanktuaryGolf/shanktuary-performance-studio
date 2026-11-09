"""The approved ribbon logo stays sharp without altering navigation."""

import pytest

from src.ui.concept_shell import GROUPS, _brand_mark_pixels


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 1.75, 2])
def test_brand_mark_uses_device_resolution_and_real_transparency(scale):
    image = _brand_mark_pixels(scale)
    assert image.mode == "RGBA"
    assert image.width <= round(43 * scale)
    assert image.height <= round(64 * scale)
    low, high = image.getchannel("A").getextrema()
    assert low == 0 and high > 240
    assert any(0 < alpha < 255 for alpha in image.getchannel("A").getdata())


def test_refined_brand_mark_keeps_merged_overview_navigation():
    modes = [mode for _, entries in GROUPS for mode, _ in entries]
    assert 12 in modes and 9 not in modes
