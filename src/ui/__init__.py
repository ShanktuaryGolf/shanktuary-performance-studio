"""Desktop UI layer for Shanktuary Performance Studio.

`ShanktuaryDesktopApp` is the production app with the approved desktop visual
system applied on top of the hardware/data/persistence implementation in
`shanktuary_performance_studio.ShanktuaryApp`.
"""

from .desktop import ShanktuaryDesktopApp
from .splash import SplashScreen, should_show_splash

__all__ = ["ShanktuaryDesktopApp", "SplashScreen", "should_show_splash"]
