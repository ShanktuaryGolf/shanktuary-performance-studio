# Walkthrough - Nova Developer Program: IR Camera Frame Visualization & Labeling Pipeline

The **Nova Inner Developer Challenge (`viz_project.md`)** solution has been built, tested, and executed across all **117 raw IR camera frame sample directories**!

📁 **Local Workspace Directory:** `/home/sean/sps/`  
📜 **Implementation Plan:** [docs/superpowers/plans/2026-08-20-nova-ir-vision-lab.md](file:///home/sean/sps/docs/superpowers/plans/2026-08-20-nova-ir-vision-lab.md)  
🔬 **Vision Lab Script:** [nova_vision_lab.py](file:///home/sean/sps/nova_vision_lab.py)

---

## 🌟 Dual-Pipeline Implementation Highlights

### 1. 🎨 Use Case 1: User-Facing Visualization (Aesthetic Composite)
- **Flat-Field Radial Vignetting Compensation:** Radial gain curve ($1.0 + 1.2 \cdot (r/r_{max})^2$) equalizes IR ring light center hot-spots and dark corner falloff (`inverse-square law`).
- **Bilateral Noise Filtering ($d=7, \sigma=50$):** Smooths low-light IR sensor grain without blurring sharp ball dimples or clubface lines.
- **CLAHE + Gamma Lifting ($\gamma = 0.75$):** Boosts local contrast and shadow detail so golfers can see themselves, their environment, and their club clearly in the background.
- **16:9 Dual-Lens Composite:** Stitches `Left` + `Right` IR frames into a 16:9 composite saved to `/home/sean/sps/output_user_facing/`.

### 2. 🔍 Use Case 2: Internal Data Labeling (Clarity & Edge Detail)
- **High-Gain Shadow Boost ($\gamma = 0.50$):** Maximizes visibility into pitch-black corners and edges for AI labelers.
- **Laplacian Edge Sharpening:** Accentuates subtle ball boundaries, spin dots, and clubhead edges.
- **Neon Mask Blending:** Blends segmentation masks (`masks/*.png`) in high-contrast neon green (`#00FF66`). Saved to `/home/sean/sps/output_labeler/`.

---

## 🧪 Automated Verification & Output Results

```text
tests/test_vision_lab.py::test_enhance_user_facing PASSED                [ 50%]
tests/test_vision_lab.py::test_enhance_labeler PASSED                    [100%]

============================== 2 passed in 0.08s ===============================
[✓] Successfully processed 117 sample shot directories!
📁 User-Facing Composites: /home/sean/sps/output_user_facing/
📁 Internal Labeler Images: /home/sean/sps/output_labeler/
```

---

## 📜 Ledger of Rulings Made:
1. **Flat-Field Gain Threshold:** Applied $1.2 \times$ radial multiplier to achieve full corner illumination without blowing out white golf balls.
2. **Dual-Lens Composite Format:** Joined left and right camera channels horizontally into 16:9 aspect ratio images ideal for phone, desktop, and projector displays.
