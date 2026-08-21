# Implementation Plan - Nova Developer Program: Raw IR Camera Frame Visualization & Labeling Pipeline

## Goal Description
Build an **Advanced IR Image Enhancement & Visualization Suite (`nova_vision_lab.py`)** to solve the official **OpenLaunch Nova Inner Developers Program Image Visualization Challenge** (`viz_project.md`).

The Nova launch monitor captures raw mono IR sensor outputs (`left_0.png`, `right_0.png`) using an IR ring light in low/zero ambient light.

---

## User Review Required

> [!IMPORTANT]
> **Dual Pipeline Strategy (`viz_project.md`):**
> 1. **Use Case 1: User-Facing Visualization (Aesthetic Composite):**
>    - **Goal:** Look crisp, cinematic, and visually impressive on phones, desktops, and floor projectors.
>    - **Techniques:** Flat-field IR vignetting correction (radial falloff compensation), CLAHE (Contrast Limited Adaptive Histogram Equalization), Bilateral Denoising, Gamma Curve Lifting ($\gamma = 0.75$), and Stereo Dual-Lens Composite Stitching (`Left` + `Right` merged into a seamless 16:9 frame).
> 2. **Use Case 2: Internal Data Labeling (Clarity & Edge Detail):**
>    - **Goal:** Maximum visibility into pitch-black corners, edges, ball dimples, and clubhead boundaries for AI labelers.
>    - **Techniques:** Adaptive High-Gain Shadow Lift ($\gamma = 0.50$), Unsharp Masking / Laplacian Edge Enhancement, and Semi-Transparent Neon Mask Overlay (`masks/*.png`).

---

## Proposed Changes

### File: `/home/sean/sps/nova_vision_lab.py`

#### [NEW] `nova_vision_lab.py`
Standalone Python script leveraging OpenCV, NumPy, and PIL to:
1. Load raw mono IR frames from `/home/sean/Pictures/golf_studio/chad_images/`.
2. Apply **User-Facing Aesthetic Pipeline**:
   - Flat-field radial gain correction to eliminate IR ring light hot-spots and dark corners.
   - Bilateral noise filtering to remove high-ISO sensor grain.
   - CLAHE + Gamma curve adjustment to reveal background environment.
   - Side-by-side 16:9 composite stitching.
3. Apply **Internal Data Labeling Pipeline**:
   - High-contrast edge enhancement.
   - Deep shadow boost ($\gamma = 0.50$).
   - Semi-transparent neon mask overlay blending (`masks/`).
4. Generate comparison output images and evaluation report.

---

### File: `/home/sean/sps/shanktuary_performance_studio.py`

#### [MODIFY] `shanktuary_performance_studio.py`
Integrate raw IR camera inspection mode into Shanktuary Performance Studio so users and developers can view enhanced live IR camera frames directly in the UI!

---

## Verification Plan

### Local Automated Verification
1. Run `nova_vision_lab.py` across all 117 sample shot directories:
   ```bash
   python3 /home/sean/sps/nova_vision_lab.py --dir /home/sean/Pictures/golf_studio/chad_images/
   ```
2. Verify output image generation:
   - User-facing composites saved to `/home/sean/sps/output_user_facing/`
   - Labeler clarity images saved to `/home/sean/sps/output_labeler/`

### Local Manual Verification
1. Inspect generated user-facing composite images vs raw `left_0.png` / `right_0.png`.
2. Confirm dark corners are illuminated, background environment is visible, and clubface/ball details are sharp and noise-free.
