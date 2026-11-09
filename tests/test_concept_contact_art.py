"""A display finish must not change the production contact coordinate model."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageOps

from src.analytics.strike import FaceGeometry
from src.ui import concept_art


def source_pixels():
    path = Path(__file__).resolve().parents[1] / "assets" / "iron_face.png"
    with Image.open(path) as source:
        return source.convert("RGBA")


def test_graphite_finish_preserves_exact_source_alpha_and_dimensions():
    source = source_pixels()
    before = source.tobytes()
    graphite = concept_art.graphite_contact_pixels(source)

    assert source.tobytes() == before
    assert graphite.size == source.size == (290, 220)
    assert graphite.getchannel("A").tobytes() == source.getchannel("A").tobytes()
    assert graphite.getchannel("A").getbbox() == (0, 4, 290, 132)
    assert graphite.convert("RGB").tobytes() != source.convert("RGB").tobytes()
    # Mid-tones darken while polished highlights remain lighter than grooves.
    ramp = Image.new("RGBA", (3, 1))
    ramp.putdata([(40, 40, 40, 255), (170, 170, 170, 255), (245, 245, 245, 255)])
    shaded = concept_art.graphite_contact_pixels(ramp)
    luminance = [shaded.convert("L").getpixel((x, 0)) for x in range(3)]
    assert luminance[0] < luminance[1] < luminance[2]
    assert luminance[1] < 80
    assert luminance[2] > 190


def test_graphite_finish_preserves_left_handed_mirroring():
    source = source_pixels()
    mirrored_first = concept_art.graphite_contact_pixels(ImageOps.mirror(source))
    shaded_first = ImageOps.mirror(concept_art.graphite_contact_pixels(source))
    assert mirrored_first.tobytes() == shaded_first.tobytes()


@pytest.mark.parametrize("left_handed", [False, True])
@pytest.mark.parametrize("size", [120, 220, 320])
def test_visible_finish_keeps_virtual_origin_and_contact_mapping(
    monkeypatch, left_handed, size
):
    pixels = source_pixels()
    if left_handed:
        pixels = ImageOps.mirror(pixels)
    pixels = pixels.resize((int(290 * size / 220), size), Image.Resampling.LANCZOS)
    monkeypatch.setattr(concept_art.ImageTk, "getimage", lambda image: image.copy())
    monkeypatch.setattr(concept_art.ImageTk, "PhotoImage", lambda image, master: image)
    app = SimpleNamespace(root=object())

    steel, steel_dx, steel_dy = concept_art.visible_contact_art(app, pixels)
    graphite, graphite_dx, graphite_dy = concept_art.visible_contact_art(
        app, pixels, dark=True
    )
    assert (steel_dx, steel_dy) == (graphite_dx, graphite_dy)
    assert steel.size == graphite.size
    assert steel.getchannel("A").tobytes() == graphite.getchannel("A").tobytes()
    assert concept_art.visible_contact_art(app, pixels)[0] is steel
    assert concept_art.visible_contact_art(app, pixels, dark=True)[0] is graphite
    assert len(app._concept_contact_cache) == 2

    geometry = FaceGeometry(cx=500, cy=300, size=size, left_handed=left_handed)
    for horizontal, vertical in ((0, 0), (-20, 12), (8, -4), (23.5, 15.5)):
        x, y = geometry.mm_to_px(horizontal, vertical)
        assert geometry.px_to_mm(x, y) == pytest.approx((horizontal, vertical))
        # A point in the sprite is in the identical place in both trimmed
        # appearances. The appearance filter has no alternative mapping.
        steel_local = (x - geometry.cx - steel_dx, y - geometry.cy - steel_dy)
        graphite_local = (
            x - geometry.cx - graphite_dx,
            y - geometry.cy - graphite_dy,
        )
        assert graphite_local == steel_local
