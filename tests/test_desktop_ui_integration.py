from src.ui.desktop import ShanktuaryDesktopApp, _aim_corrected_display_shots
import shanktuary_performance_studio as production


def test_desktop_app_is_visual_subclass_of_production_app():
    assert issubclass(ShanktuaryDesktopApp, production.ShanktuaryApp)


def test_display_aim_context_restores_native_session_payloads():
    native = {"id": "shot-1", "open_golf_coach": {"shot_name": "Push Fade"}}

    class Dummy:
        def __init__(self):
            self.sessions = [{"shots": [native]}]
            self.active_session_index = 0
            self.selected_shot_index = 0
            self.current_shot = native

        def get_active_session(self):
            return self.sessions[self.active_session_index]

        def aim_corrected(self, shot):
            out = dict(shot)
            out["display_corrected"] = True
            return out

    app = Dummy()
    original_list = app.sessions[0]["shots"]

    with _aim_corrected_display_shots(app):
        assert app.current_shot is app.sessions[0]["shots"][0]
        assert app.current_shot["display_corrected"] is True
        assert app.sessions[0]["shots"] is not original_list

    assert app.sessions[0]["shots"] is original_list
    assert app.sessions[0]["shots"][0] is native
    assert app.current_shot is native
    assert "display_corrected" not in native
