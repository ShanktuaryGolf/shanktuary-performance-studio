"""Club background fix for the navy/teal/gold palette pass.

v2 exposed a production-layout quirk: the original Club renderer does not
paint four panel backgrounds. The v1 polish layer *does* use background-colored
cleanup masks and fully redraws the two right quadrants, so recoloring only the
polish layer created visible navy rectangles over the legacy near-black canvas.

This pass establishes one continuous Club-local canvas before any production
or polish drawing happens. The existing v2 palette and all accepted Club-page
hierarchy/credibility changes remain untouched.
"""

import club_redesign_v2 as v2


# Keep this exactly aligned with the cleanup/redraw background used by v2/v1.
CLUB_BG = v2.CLUB_BG


def draw_top_metric_toolbar(app, *args, **kwargs):
    return v2.draw_top_metric_toolbar(app, *args, **kwargs)


def draw_4_quadrant_studio(app, production_draw, *args, **kwargs):
    """Lay down one continuous Club canvas, then draw the accepted v2 page."""
    # Signature begins: avail_w, h, ...; offset_x/top_bar_h may be kwargs or
    # positional production defaults. The launcher passes through unchanged.
    avail_w = args[0] if len(args) > 0 else kwargs.get("avail_w", 0)
    h = args[1] if len(args) > 1 else kwargs.get("h", 0)
    offset_x = kwargs.get("offset_x", 0)
    top_bar_h = kwargs.get("top_bar_h", 108)

    # If these optional args arrived positionally, mirror production's order:
    # ... smash, ball_speed=0.0, offset_x=0, top_bar_h=108
    if len(args) >= 20:
        offset_x = args[19]
    if len(args) >= 21:
        top_bar_h = args[20]

    # Production only draws dividers/graphics in this region, so establishing
    # the page material here removes every legacy-black pocket and makes all
    # v1 cleanup masks visually disappear into the canvas.
    app.canvas.create_rectangle(
        offset_x, top_bar_h, offset_x + avail_w, h - 10,
        fill=CLUB_BG, outline="",
    )

    return v2.draw_4_quadrant_studio(
        app, production_draw, *args, **kwargs
    )
