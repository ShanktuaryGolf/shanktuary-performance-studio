"""Navigate public concept controls in graphical integration tests."""
from types import SimpleNamespace


def click_rect(app, rect):
    assert rect and rect[2] > rect[0] and rect[3] > rect[1]
    app.handle_mouse_press(SimpleNamespace(x=(rect[0]+rect[2])/2,
                                          y=(rect[1]+rect[3])/2))


def open_setup_details(app):
    """Go through the same overview → Details action as a user."""
    app.set_mode(10)
    if getattr(app, 'concept_setup_page', 'overview') != 'details':
        click_rect(app, app.concept_setup_actions['details'])
    assert app.concept_setup_page == 'details'
    assert 'overview' in app.concept_setup_actions
