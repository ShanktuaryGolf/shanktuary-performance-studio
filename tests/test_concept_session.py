"""Renderer contracts run without a display or physical hardware."""
from copy import deepcopy

from src.ui import concept_session as ui


class Canvas:
    def __init__(self):
        self.items=[]

    def __getattr__(self,name):
        if name.startswith('create_'):
            def create(*coords,**kw):
                self.items.append((name,coords,kw))
                return len(self.items)
            return create
        raise AttributeError(name)


class App:
    def __init__(self,shots):
        self.canvas=Canvas()
        self.session_shots=shots
        self.current_shot=shots[-1] if shots else None
        self.selected_shot_index=len(shots)-1
        self.land_dot_coords=[]
        self.is_left_handed=False

    def aim_corrected(self,shot):
        return deepcopy(shot)

    def get_scaled_club_asset(self,*a,**kw):
        return None


def test_missing_values_are_unavailable_and_no_flight_is_invented():
    app=App([{'_source':'pureplay','club':'7 iron'}])
    ui.draw_shot(app,1320,900,260)
    texts=[kw.get('text') for _,_,kw in app.canvas.items]
    assert 'Trajectory unavailable' in texts
    assert 'Impact unavailable' in texts
    assert 'Unavailable' in texts
    assert app.land_dot_coords == []
    assert app.contact_face_rect is not None  # manual contact marking still works


def test_shot_renderer_does_not_mutate_payload_and_registers_shot_selection():
    shots=[{'club':'7 iron','ball_speed_meters_per_second':50,'vertical_launch_angle_degrees':18,
            'total_spin_rpm':6400,'open_golf_coach':{'shot_name':'Draw','us_customary_units':{
                'carry_distance_yards':150+i,'peak_height_yards':28,'offline_distance_yards':i-2}}} for i in range(5)]
    before=deepcopy(shots)
    app=App(shots)
    ui.draw_shot(app,1320,900,260)
    assert shots==before
    assert len(app.design_shot_card_rects)==4
    assert len(app.land_dot_coords)==5
    assert app.design_shot_card_rects[0][-1]==4


def test_club_renders_empty_state_without_fake_measured_club_data():
    app=App([])
    ui.draw_club(app,1320,900,260)
    texts=[kw.get('text') for _,_,kw in app.canvas.items]
    assert 'Impact unavailable' in texts
    assert 'Trajectory unavailable' in texts
    assert app.contact_face_rect is None


def test_zero_is_preserved_as_a_reported_value():
    app=App([{'horizontal_launch_angle_degrees':0.0}])
    assert ui.value(app,app.current_shot,'horizontal_launch')==0
    assert ui.number(0,'°',1)=='0.0 °'
    assert ui.status(app,app.current_shot,'horizontal_launch')=='Reported'


def test_session_navigation_and_delete_use_existing_actions():
    app=App([{'club':'7 iron'} for _ in range(6)])
    app.draw_screen=lambda: None
    deleted=[]
    app.delete_shot=lambda index: deleted.append(index)
    ui.draw_shot(app,1320,900,260)
    rect,_,_=next(row for row in app.concept_session_rects if row[1]=='step' and row[2]==-1)
    assert ui.handle_session_click(app,(rect[0]+rect[2])/2,(rect[1]+rect[3])/2)
    assert app.selected_shot_index==4
    ui.draw_shot(app,1320,900,260)
    rect,_,_=next(row for row in app.concept_session_rects if row[1]=='delete')
    assert ui.handle_session_click(app,(rect[0]+rect[2])/2,(rect[1]+rect[3])/2)
    assert deleted==[4]


def test_contact_markers_and_history_estimates_keep_distinct_tags():
    shots=[{'club':'7 iron'}, {'club':'7 iron','marked_contact':{'horizontal_mm':8.0,'vertical_mm':-4.0}}]
    app=App(shots)
    app.selected_shot_index=0
    app.current_shot=shots[0]
    ui.contact(app,(0,0,450,300))
    tags=[kw.get('tags') for _,_,kw in app.canvas.items]
    assert 'contact-peer' in tags
    assert 'contact-estimate' in tags
    assert 'contact-marker' not in tags
    app.canvas=Canvas()
    app.current_shot=shots[1]
    ui.contact(app,(0,0,450,300))
    tags=[kw.get('tags') for _,_,kw in app.canvas.items]
    assert 'contact-marker' in tags
    assert 'contact-estimate' not in tags
    assert app.contact_clear_rect is not None


def test_estimated_source_metrics_keep_provenance():
    shot={'ball_speed_meters_per_second':40,'_metric_provenance':{
        'ball_speed_meters_per_second':{'kind':'source_estimated'}}}
    app=App([shot])
    assert ui.status(app,shot,'ball_speed')=='Estimate'
    assert ui.value(app,shot,'club_path') is None
