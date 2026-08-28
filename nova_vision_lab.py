"""Nova IR vision lab -- offline analysis tool, not part of the shipped app.

Deliberately NOT in requirements.txt: the desktop app and obs_server never
import cv2 or numpy, and forcing every Nova owner to pull OpenCV to run the
launch monitor would be a large dependency for a tool most will never use.

    python3 -m pip install opencv-python numpy

Input/output paths come from NOVA_CAPTURE_DIR / NOVA_OUTPUT_DIR or from the
function arguments -- see process_all_chad_images().
"""
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

def enhance_nova_official_aesthetic(img_l, img_r):
    """
    Reverse-Engineered 1-to-1 Match for Nova Official C++ Dashboard Pipeline (example.png)
    - 3x3 Median Denoising
    - Shared Stereo Peak Scaling
    - Logarithmic Compress-Expand Tone Mapping (k = 15.0)
    - Black Baseline Offset (min = 16) for dark-mode UI blending
    """
    # 1. Median filter to eliminate single-pixel salt-and-pepper noise
    clean_l = cv2.medianBlur(img_l, 3)
    clean_r = cv2.medianBlur(img_r, 3)

    # 2. Flat-field radial vignetting compensation
    flat_l = apply_flat_field_correction(clean_l)
    flat_r = apply_flat_field_correction(clean_r)

    # 3. Shared max scaling across stereo pair
    shared_max = float(max(flat_l.max(), flat_r.max(), 10))

    # 4. Logarithmic Tone Mapping Curve: log(1 + k*x) / log(1 + k)
    k = 15.0
    log_l = np.log1p(k * (flat_l.astype(np.float32) / shared_max)) / np.log1p(k)
    log_r = np.log1p(k * (flat_r.astype(np.float32) / shared_max)) / np.log1p(k)

    # 5. Map to [16, 255] for baseline shadow offset matching example.png
    res_l = np.clip(16.0 + log_l * 239.0, 16, 255).astype(np.uint8)
    res_r = np.clip(16.0 + log_r * 239.0, 16, 255).astype(np.uint8)

    composite = np.hstack((res_l, res_r))
    bgr = cv2.cvtColor(composite, cv2.COLOR_GRAY2BGR)
    return bgr

def enhance_labeler(img_mono, mask=None):
    clean = cv2.medianBlur(img_mono, 3)
    img_max = float(max(clean.max(), 10))
    norm = np.clip(clean.astype(np.float32) / img_max * 255.0, 0, 255).astype(np.uint8)
    flat = apply_flat_field_correction(norm)

    gamma = 0.40
    table = np.array([((i / 255.0) ** gamma) * 255 for i in range(256)]).astype("uint8")
    shadow_lifted = cv2.LUT(flat, table)

    laplacian = cv2.Laplacian(shadow_lifted, cv2.CV_8U, ksize=3)
    sharpened = cv2.addWeighted(shadow_lifted, 0.85, laplacian, 0.35, 0)
    bgr = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)

    if mask is not None:
        colored_mask = np.zeros_like(bgr)
        colored_mask[mask > 0] = [0, 255, 102]  # Neon Green
        bgr = cv2.addWeighted(bgr, 0.75, colored_mask, 0.35, 0)
    return bgr

def process_all_chad_images(chad_dir=None, out_root=None):
    """Batch-process Nova IR capture directories into review composites.

    Paths are arguments, not constants: this is a dev/analysis tool that
    other Nova owners may run against their own captures. Defaults come from
    the environment, then fall back to a directory beside this script.

        NOVA_CAPTURE_DIR  input, dirs each containing left_0.png/right_0.png
        NOVA_OUTPUT_DIR   where composites are written

    Output is untracked user data: filenames carry per-user account IDs, so
    it stays out of the repo (see .gitignore).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    chad_dir = (chad_dir or os.environ.get("NOVA_CAPTURE_DIR")
                or os.path.join(here, "nova_captures"))
    out_root = (out_root or os.environ.get("NOVA_OUTPUT_DIR") or here)

    user_out = os.path.join(out_root, "output_user_facing")
    labeler_out = os.path.join(out_root, "output_labeler")
    os.makedirs(user_out, exist_ok=True)
    os.makedirs(labeler_out, exist_ok=True)

    if not os.path.isdir(chad_dir):
        print(f"[!] Capture directory not found: {chad_dir}")
        print("    Set NOVA_CAPTURE_DIR or pass chad_dir=...")
        return 0

    dirs = [d for d in glob.glob(os.path.join(chad_dir, "*")) if os.path.isdir(d)]
    print(f"[+] Re-processing {len(dirs)} sample directories with 1-to-1 Nova Official Dashboard Pipeline...")
    count = 0
    for d in dirs:
        folder_name = os.path.basename(d)
        left_path = os.path.join(d, "left_0.png")
        right_path = os.path.join(d, "right_0.png")

        if os.path.exists(left_path) and os.path.exists(right_path):
            img_l = cv2.imread(left_path, cv2.IMREAD_GRAYSCALE)
            img_r = cv2.imread(right_path, cv2.IMREAD_GRAYSCALE)

            composite_16_9 = enhance_nova_official_aesthetic(img_l, img_r)
            cv2.imwrite(os.path.join(user_out, f"{folder_name}_composite.jpg"), composite_16_9)

            mask = None
            mask_path = os.path.join(d, "masks", "mask.png")
            if os.path.exists(mask_path):
                mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

            lbl_l = enhance_labeler(img_l, mask)
            cv2.imwrite(os.path.join(labeler_out, f"{folder_name}_left_labeler.png"), lbl_l)
            count += 1

    print(f"[✓] Successfully re-processed {count} sample shot directories matching Nova Official Dashboard!")

if __name__ == "__main__":
    process_all_chad_images()
