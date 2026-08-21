import os, numpy as np, pytest
from nova_vision_lab import enhance_nova_official_aesthetic, enhance_labeler

def test_enhance_nova_official_aesthetic():
    dummy_l = np.zeros((480, 640), dtype=np.uint8)
    dummy_r = np.zeros((480, 640), dtype=np.uint8)
    dummy_l[200:280, 280:360] = 180
    dummy_r[200:280, 280:360] = 150
    enhanced = enhance_nova_official_aesthetic(dummy_l, dummy_r)
    assert enhanced.shape == (480, 1280, 3)
    assert enhanced.dtype == np.uint8

def test_enhance_labeler():
    dummy = np.zeros((480, 640), dtype=np.uint8)
    dummy[200:280, 280:360] = 180
    enhanced = enhance_labeler(dummy)
    assert enhanced.shape == (480, 640, 3)
    assert enhanced.dtype == np.uint8
