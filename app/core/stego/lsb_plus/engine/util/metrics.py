from __future__ import annotations
import numpy as np
from numba import njit
from scipy import ndimage

# =============================================================================
# 1. JIT HELPERS (ทำงานระดับ Machine Code เพื่อความเร็วสูงสุด)
# =============================================================================

@njit(cache=True)
def _to_gray_jit(img: np.ndarray) -> np.ndarray:
    """แปลง RGB เป็น Gray (Float32)"""
    if img.ndim == 2:
        return img.astype(np.float32)
    h, w = img.shape[:2]
    gray = np.empty((h, w), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            gray[y, x] = 0.299 * img[y, x, 0] + 0.587 * img[y, x, 1] + 0.114 * img[y, x, 2]
    return gray

@njit(cache=True)
def _calc_hist_stats_jit(o_gray, s_gray, density=False):
    """คำนวณ Histogram Stats (Drift & Chi-Square)"""
    # ใช้ Array เล็กๆ เก็บ bin เพื่อความเร็ว
    ho = np.zeros(256, dtype=np.float64)
    hs = np.zeros(256, dtype=np.float64)
    
    fo = o_gray.ravel()
    fs = s_gray.ravel()
    size = fo.size
    
    # 1. Loop เดียวจบ เร็วกว่า np.histogram มาก
    for i in range(size):
        ho[int(fo[i])] += 1
        hs[int(fs[i])] += 1
        
    if density:
        ho /= size
        hs /= size
        
    drift = 0.0
    for i in range(256):
        drift += abs(ho[i] - hs[i])
        
    chi_sq = 0.0
    if not density:
        for i in range(256):
            expected = ho[i] + 1e-3
            chi_sq += ((hs[i] - ho[i])**2) / expected
            
    return drift, chi_sq

@njit(cache=True)
def _psnr_jit(orig, stego):
    """คำนวณ PSNR แบบ Pixel-wise (ไม่กิน RAM)"""
    h, w, c = orig.shape
    sum_sq = 0.0
    count = h * w * c
    
    # Loop คำนวณผลรวมความต่างยกกำลังสองโดยตรง
    for y in range(h):
        for x in range(w):
            for k in range(c):
                diff = float(orig[y, x, k]) - float(stego[y, x, k])
                sum_sq += diff * diff
                
    mse = sum_sq / count
    if mse <= 1e-12:
        return 999.0 # Infinity
    
    return 20.0 * np.log10(255.0) - 10.0 * np.log10(mse)

@njit(cache=True)
def _ssim_combine_jit(mu_x, mu_y, sigma_x2, sigma_y2, sigma_xy, C1, C2):
    """รวมผลลัพธ์ SSIM (สูตรเดิม 100%) ใน JIT เพื่อลดการใช้ RAM"""
    h, w = mu_x.shape
    ssim_sum = 0.0
    
    for y in range(h):
        for x in range(w):
            mx = mu_x[y, x]
            my = mu_y[y, x]
            sx2 = sigma_x2[y, x]
            sy2 = sigma_y2[y, x]
            sxy = sigma_xy[y, x]
            
            mx2 = mx * mx
            my2 = my * my
            mxy = mx * my
            
            # คำนวณ Variance จริง: E[x^2] - (E[x])^2
            vx2 = sx2 - mx2
            vy2 = sy2 - my2
            vxy = sxy - mxy
            
            num = (2 * mxy + C1) * (2 * vxy + C2)
            den = (mx2 + my2 + C1) * (vx2 + vy2 + C2)
            
            ssim_sum += num / (den + 1e-12)
            
    return ssim_sum / (h * w)

# =============================================================================
# 3. PUBLIC FUNCTIONS (เรียกใช้งานจากภายนอก)
# =============================================================================

def compute_psnr(orig: np.ndarray, stego: np.ndarray) -> float:
    # เรียก JIT kernel
    return float(_psnr_jit(orig, stego))

def compute_ssim(orig: np.ndarray, stego: np.ndarray) -> float:
    # 1. เตรียมภาพ Grayscale
    x = _to_gray_jit(orig)
    y = _to_gray_jit(stego)
    
    C1 = 6.5025
    C2 = 58.5225
    
    # 2. เตรียม 1D Gaussian Kernel (สำหรับ Separable Convolution)
    # [Optimization] การทำ 1D Conv สองครั้ง เร็วกว่า 2D Conv หนึ่งครั้งมากๆ
    win_size = 11
    sigma = 1.5
    ax = np.arange(-win_size // 2 + 1., win_size // 2 + 1.)
    gauss = np.exp(-0.5 * np.square(ax) / np.square(sigma))
    gauss /= np.sum(gauss)
    kernel = gauss.astype(np.float32)

    # ฟังก์ชันช่วยทำ 1D convolution สองแกน
    def fast_conv(img):
        tmp = ndimage.convolve1d(img, kernel, axis=0, mode='reflect')
        return ndimage.convolve1d(tmp, kernel, axis=1, mode='reflect')

    # 3. คำนวณค่าทางสถิติ (Convolution)
    mu_x = fast_conv(x)
    mu_y = fast_conv(y)
    sigma_x2 = fast_conv(x * x)
    sigma_y2 = fast_conv(y * y)
    sigma_xy = fast_conv(x * y)
    
    # 4. รวมผลลัพธ์ด้วย JIT
    return float(_ssim_combine_jit(mu_x, mu_y, sigma_x2, sigma_y2, sigma_xy, C1, C2))

def histogram_drift(orig: np.ndarray, stego: np.ndarray) -> float:
    o_gray = _to_gray_jit(orig).astype(np.uint8)
    s_gray = _to_gray_jit(stego).astype(np.uint8)
    drift, _ = _calc_hist_stats_jit(o_gray, s_gray, density=True)
    return float(drift)

# --- Block Metrics (เรียกใช้ฟังก์ชันหลัก เพื่อความสม่ำเสมอ) ---

def histogram_drift_block(orig_block: np.ndarray, stego_block: np.ndarray) -> float:
    return histogram_drift(orig_block, stego_block)

def variance_ratio_block(orig_block: np.ndarray, stego_block: np.ndarray) -> float:
    go = _to_gray_jit(orig_block)
    gs = _to_gray_jit(stego_block)
    vo, vs = go.var(), gs.var()
    if vo < 1e-6: return 0.0
    return float(abs(vs - vo) / (vo + 1e-6))

def chi_square_block(orig_block: np.ndarray, stego_block: np.ndarray) -> float:
    o_gray = _to_gray_jit(orig_block).astype(np.uint8)
    s_gray = _to_gray_jit(stego_block).astype(np.uint8)
    _, chi_sq = _calc_hist_stats_jit(o_gray, s_gray, density=False)
    return float(chi_sq)