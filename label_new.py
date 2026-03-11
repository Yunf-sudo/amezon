import os
import warnings

# 1. 强制禁用损坏的 xformers 加速器，防止输出脏数据（关键！）
os.environ["XFORMERS_DISABLED"] = "1"
warnings.filterwarnings("ignore")

import cv2
import torch
import numpy as np
from PIL import Image, ImageFile
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
# from segment_anything import build_sam, SamPredictor

# 允许读取损坏截断的图片
ImageFile.LOAD_TRUNCATED_IMAGES = True 

# ================= 1. 核心配置区 =================
IMAGE_DIR = "Abed"                   # 你的床的图片文件夹 (改成你实际的名字)
OUTPUT_LABEL_DIR = "Abed_labels"     # 纯净标签输出文件夹

# 🌟 床的通缉令：强调整体，同时把床头柜、衣柜、地毯加进去做“避雷针”
TEXT_PROMPT = "a complete bed . a whole double bed . a single bed . a nightstand . a bedside table . a wardrobe . a rug ."
TARGET_KEYWORDS = ["bed"]            # 我们真正想要的只有床

CLASS_ID = 0                         # 床在 dataset.yaml 里的 ID 通常是 0

BOX_THRESHOLD = 0.3              
TEXT_THRESHOLD = 0.3             

# C位清洗阈值保持不变
INTERNAL_IOA_THRESH = 0.60       # 吸收内部碎渣 (比如只框了枕头/被子)
EXTERNAL_AREA_RATIO = 0.35       # 删掉外部杂物 (比如床头柜)
# ============================================

SAM_WEIGHTS = "weights/sam_vit_h_4b8939.pth" 
# ============================================

os.makedirs(OUTPUT_LABEL_DIR, exist_ok=True)
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"🚀 正在使用 {device.upper()} 模式运行二合一标注与清洗系统...")
print("📦 正在加载纯 Python 版 GroundingDINO 和 SAM...")

# 加载本地模型 (强迫离线读取)
processor = AutoProcessor.from_pretrained("./local_gd_model/processor", local_files_only=True)
gd_model = AutoModelForZeroShotObjectDetection.from_pretrained(
    "./local_gd_model/model",
    attn_implementation="eager",
    local_files_only=True
).to(device)

# 初始化 SAM (虽然这一步没抠图，但保留你的环境完整性，为下一步备用)
# sam_predictor = SamPredictor(build_sam(checkpoint=SAM_WEIGHTS).to(device))
# print("✅ 模型加载完成！开始自动化标注与实时清洗...")

# --- 辅助计算函数 ---
def compute_ioa_and_iou(box1_coords, box2_coords, area1, area2):
    x1_min, y1_min, x1_max, y1_max = box1_coords
    x2_min, y2_min, x2_max, y2_max = box2_coords

    inter_x_min, inter_y_min = max(x1_min, x2_min), max(y1_min, y2_min)
    inter_x_max, inter_y_max = min(x1_max, x2_max), min(y1_max, y2_max)

    inter_w = max(0, inter_x_max - inter_x_min)
    inter_h = max(0, inter_y_max - inter_y_min)
    inter_area = inter_w * inter_h

    iou = inter_area / (area1 + area2 - inter_area) if (area1 + area2 - inter_area) > 0 else 0
    ioa_small_in_big = inter_area / min(area1, area2) if min(area1, area2) > 0 else 0 
    return iou, ioa_small_in_big

# ================= 2. 核心流水线 =================
for filename in os.listdir(IMAGE_DIR):
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        continue
    
    image_path = os.path.join(IMAGE_DIR, filename)
    print(f"\n---> 正在处理: {filename}")
    
    try:
        image = Image.open(image_path).convert("RGB")
        w_img, h_img = image.size
    except Exception as e:
        print(f"  ⚠️ [跳过] 图片损坏: {e}")
        continue

    # 【第一阶段】：GroundingDINO 推理
    inputs = processor(images=image, text=TEXT_PROMPT, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = gd_model(**inputs)

    results = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=BOX_THRESHOLD,
        text_threshold=TEXT_THRESHOLD,
        target_sizes=torch.tensor([[h_img, w_img]])
    )[0]

    boxes_abs = results["boxes"].tolist()
    labels = results["labels"]
    
    if not boxes_abs:
        print("  [空] 未检测到任何目标")
        continue

    # 【第二阶段】：语义过滤与构建候选框
    candidate_boxes = []
    for box, label in zip(boxes_abs, labels):
        # 1. 语义过滤：只留下带 chair/sofa 等关键词的框，扔掉 cabinet/table
        if not any(kw in label.lower() for kw in TARGET_KEYWORDS):
            continue
            
        x_min, y_min, x_max, y_max = box
        w, h = x_max - x_min, y_max - y_min
        area = w * h
        
        # 2. 极值过滤：砍掉面积不到全图 1% 的纯碎渣
        if area < (w_img * h_img * 0.01):
            continue
            
        candidate_boxes.append({
            'coords': box,
            'area': area,
            'keep': True
        })

    if not candidate_boxes:
        print("  [空] 过滤语义和噪点后，无有效目标")
        continue

    # 【第三阶段】：C位主框霸权清洗 (内嵌版)
    if len(candidate_boxes) > 1:
        # 找到画面里最大的那个框（即主商品）
        main_box = max(candidate_boxes, key=lambda x: x['area'])
        
        for box in candidate_boxes:
            if box == main_box: continue
            
            iou, ioa_small_in_big = compute_ioa_and_iou(main_box['coords'], box['coords'], main_box['area'], box['area'])
            
            # 斩杀 1：内部零件 (坐垫/扶手)
            if ioa_small_in_big > INTERNAL_IOA_THRESH:
                box['keep'] = False
            # 斩杀 2：外部背景杂物 (虽然识别成了椅子，但在旁边且很小)
            elif iou < 0.1 and box['area'] < (main_box['area'] * EXTERNAL_AREA_RATIO):
                box['keep'] = False

    # 【第四阶段】：转换 YOLO 格式并保存
    final_boxes = [b for b in candidate_boxes if b['keep']]
    
    if not final_boxes:
        continue
        
    label_filename = os.path.splitext(filename)[0] + ".txt"
    label_path = os.path.join(OUTPUT_LABEL_DIR, label_filename)
    
    with open(label_path, "w") as f:
        for b in final_boxes:
            x_min, y_min, x_max, y_max = b['coords']
            
            # 转为归一化中心点与宽高
            cx = ((x_min + x_max) / 2.0) / w_img
            cy = ((y_min + y_max) / 2.0) / h_img
            box_w = (x_max - x_min) / w_img
            box_h = (y_max - y_min) / h_img
            
            # 防越界钳制
            cx, cy = max(0, min(cx, 1)), max(0, min(cy, 1))
            box_w, box_h = max(0, min(box_w, 1)), max(0, min(box_h, 1))
            
            f.write(f"{CLASS_ID} {cx:.6f} {cy:.6f} {box_w:.6f} {box_h:.6f}\n")
            
    print(f"  ✅ [成功] 经过 C位过滤，提取了 {len(final_boxes)} 个纯净检测框")

print("\n🎉 自动化标注 + 实时智能清洗流水线，全部运行完毕！")