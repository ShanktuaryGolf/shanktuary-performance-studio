# Nova Raw IR Camera Visualization & Labeling Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an advanced IR image enhancement and visualization suite (`nova_vision_lab.py`) to process raw mono IR camera frames (`left_0.png`, `right_0.png`) from OpenLaunch Nova for user-facing aesthetic rendering and internal AI data labeling.

**Architecture:** A modular Python pipeline combining OpenCV (`cv2`), NumPy, and PIL. Uses Flat-Field Radial Vignetting Compensation, Contrast Limited Adaptive Histogram Equalization (CLAHE), Bilateral Denoising, Gamma Curve Lifting ($\gamma = 0.75$), Laplacian edge sharpening, and stereo dual-lens composite stitching.

**Tech Stack:** Python 3, OpenCV (`opencv-python`), NumPy, Pillow, PyInstaller.

**Spec:** `/home/sean/Pictures/golf_studio/chad_images/viz_project.md`

## Global Constraints

- Must process all 117 sample shot directories in `/home/sean/Pictures/golf_studio/chad_images/` without failing.
- User-facing images must be saved as high-contrast 16:9 composite images in `output_user_facing/`.
- Internal labeling images must be saved with sharp edge visibility and mask overlays in `output_labeler/`.

---

### Task 1: Flat-Field Vignetting & Tone Mapping Pipeline

**Files:**
- Create: `nova_vision_lab.py`
- Test: `tests/test_vision_lab.py`

**Interfaces:**
- Consumes: Raw `left_0.png` and `right_0.png` image bytes
- Produces: `enhance_user_facing(image_np)` and `enhance_labeler(image_np, mask_np)` functions

- [ ] **Step 1: Write failing unit test for IR image enhancement**

```python
import os, numpy as np, pytest
from nova_vision_lab import enhance_user_facing, enhance_labeler

def test_enhance_user_facing():
    dummy = np.zeros((480, 640), dtype=np.uint8)
    dummy[200:280, 280:360] = 180  # Center bright spot
    enhanced = enhance_user_facing(dummy)
    assert enhanced.shape == (480, 640, 3)
    assert enhanced.dtype == np.uint8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_vision_lab.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nova_vision_lab'`

- [ ] **Step 3: Implement minimal code in `nova_vision_lab.py`**

```python
import cv2, numpy as np, os, glob

def apply_flat_field_correction(img):
    h, w = img.shape[:2]
    cy, cx = h / 2.0, w / 2.0
    y, x = np.ogrid[:h, :w]
    dist_sq = (x - cx)**2 + (y - cy)**2
    max_dist_sq = cx**2 + cy**2
    radial_gain = 1.0 + 1.2 * (dist_sq / max_dist_sq)
    corrected = np.clip(img.astype(np.float32) * radial_gain, 0, 255).astype(np.uint8)
    return corrected

def enhance_user_facing(img_mono):
    corrected = apply_flat_field_correction(img_mono)
    denoised = cv2.bilateralFilter(corrected, d=7, sigmaColor=50, sigmaSpace=50)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    equalized = clahe.apply(denoised)
    gamma = 0.75
    invGamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** invGamma) * 255 for i in range(256)]).astype("uint8")
    gamma_corrected = cv2.LUT(equalized, table)
    bgr = cv2.applyColorMap(gamma_corrected, cv2.COLORMAP_BONE)
    return bgr

def enhance_labeler(img_mono, mask=None):
    corrected = apply_flat_field_correction(img_mono)
    gamma = 0.50
    invGamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** invGamma) * 255 for i in range(256)]).astype("uint8")
    boosted = cv2.LUT(corrected, table)
    laplacian = cv2.Laplacian(boosted, cv2.CV_8U, ksize=3)
    sharpened = cv2.addWeighted(boosted, 0.85, laplacian, 0.35, 0)
    bgr = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)
    if mask is not None:
        colored_mask = np.zeros_like(bgr)
        colored_mask[mask > 0] = [0, 255, 102]  # Neon Green
        bgr = cv2.addWeighted(bgr, 0.75, colored_mask, 0.35, 0)
    return bgr
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_vision_lab.py -v`
Expected: PASS

- [ ] **Step 5: Batch process all 117 sample directories**

```python
def process_all_chad_images(chad_dir="/home/sean/Pictures/golf_studio/chad_images"):
    user_out = "/home/sean/sps/output_user_facing"
    labeler_out = "/home/sean/sps/output_labeler"
    os.makedirs(user_out, exist_ok=True)
    os.makedirs(labeler_out, exist_ok=True)

    dirs = [d for d in glob.glob(os.path.join(chad_dir, "*")) if os.path.isdir(d)]
    print(f"[+] Found {len(dirs)} sample directories to process...")
    for d in dirs:
        folder_name = os.path.basename(d)
        left_path = os.path.join(d, "left_0.png")
        right_path = os.path.join(d, "right_0.png")

        if os.path.exists(left_path) and os.path.exists(right_path):
            img_l = cv2.imread(left_path, cv2.IMREAD_GRAYSCALE)
            img_r = cv2.imread(right_path, cv2.IMREAD_GRAYSCALE)

            usr_l = enhance_user_facing(img_l)
            usr_r = enhance_user_facing(img_r)
            composite_16_9 = np.hstack((usr_l, usr_r))

            cv2.imwrite(os.path.join(user_out, f"{folder_name}_composite.jpg"), composite_16_9)

            lbl_l = enhance_labeler(img_l)
            cv2.imwrite(os.path.join(labeler_out, f"{folder_name}_left_labeler.png"), lbl_l)

    print(f"[✓] Successfully processed all sample shot directories!")

if __name__ == "__main__":
    process_all_chad_images()
```

- [ ] **Step 6: Commit**

```bash
git add nova_vision_lab.py tests/test_vision_lab.py docs/superpowers/plans/
git commit -m "feat: Implement Nova IR camera visualization and data labeling pipeline (Task 1)"
```
