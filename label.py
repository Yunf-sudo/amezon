import os
import warnings

# 1. 强制禁用损坏的 xformers 加速器
os.environ["XFORMERS_DISABLED"] = "1"
warnings.filterwarnings("ignore")

import torch
import numpy as np
from PIL import Image, ImageFile
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

# 允许读取损坏截断的图片
ImageFile.LOAD_TRUNCATED_IMAGES = True 

# ================= 1. 核心配置区 =================
IMAGE_DIR = "C"          # 你的图片文件夹
OUTPUT_LABEL_DIR = "C_lable"   # 生成的 YOLO 标签保存路径

# 🌟 关键修改 1：重构 Prompt（加入语义隔离/负向提示词）
# 我们不仅要找梁（单数），还要找灯和壁炉架，用来做“物理消杀”
TEXT_PROMPT = "a single structural ceiling beam . one individual wooden joist . a chandelier . a light fixture . a fireplace mantel ."

# 关键词分类清单（用于区分哪些是我们要的，哪些是用来排雷的）
TARGET_KEYWORDS = ["beam", "joist"]
NEGATIVE_KEYWORDS = ["chandelier", "light", "fixture", "mantel"]

CLASS_ID = 14            # YOLO 类别 ID (横梁)

BOX_THRESHOLD = 0.25     # 放宽一点置信度，靠后面的清洗逻辑来兜底
TEXT_THRESHOLD = 0.25    

# 🌟 关键修改 2：硬核几何过滤阈值
MAX_AREA_RATIO = 0.35    # 面积封顶：框的面积超过全图 35% 直接斩杀（对付满屏打包框）
NEG_IOU_THRESH = 0.30    # 语义隔离：和灯/壁炉架的重合度超过 30% 直接斩杀（对付误杀）
NMS_IOU_THRESH = 0.60    # 重叠消除：两根梁的框重合度超过 60%，删掉其中一个（对付重复画框）
# ============================================

os.makedirs(OUTPUT_LABEL_DIR, exist_ok=True)
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"🚀 启动 2.0 版抗噪自动标注系统 (运行于 {device.upper()})...")

# 离线加载模型
processor = AutoProcessor.from_pretrained("./local_gd_model/processor", local_files_only=True)
gd_model = AutoModelForZeroShotObjectDetection.from_pretrained(
    "./local_gd_model/model",
    attn_implementation="eager",
    local_files_only=True
).to(device)

# --- 辅助函数：计算交并比 (IoU) ---
def compute_iou(box1, box2):
    # box 格式: [x_min, y_min, x_max, y_max]
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    
    if area1 + area2 - inter_area <= 0: return 0
    return inter_area / (area1 + area2 - inter_area)


# ================= 🚀 开始流水线 =================
for filename in os.listdir(IMAGE_DIR):
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        continue
    
    image_path = os.path.join(IMAGE_DIR, filename)
    print(f"\n---> 正在处理: {filename}")
    
    try:
        image = Image.open(image_path).convert("RGB")
        w_img, h_img = image.size
    except Exception as e:
        print(f"  ⚠️ [警告] 图片损坏，跳过: {filename} (原因: {e})")
        continue

    # GroundingDINO 推理
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
    labels = results["labels"] # 拿到每个框对应的文字标签

    if not boxes_abs:
        print(f"  [跳过] 未检测到任何目标")
        continue

    # ================= 🧼 清洗第一步：分类提取 =================
    raw_targets = []
    negatives = []
    
    for box, label in zip(boxes_abs, labels):
        label_text = label.lower()
        if any(kw in label_text for kw in TARGET_KEYWORDS):
            raw_targets.append(box)
        elif any(kw in label_text for kw in NEGATIVE_KEYWORDS):
            negatives.append(box)
            
    # ================= 🧼 清洗第二步：面积封顶法 =================
    area_filtered_targets = []
    for box in raw_targets:
        box_area = (box[2] - box[0]) * (box[3] - box[1])
        area_ratio = box_area / (w_img * h_img)
        if area_ratio <= MAX_AREA_RATIO:
            area_filtered_targets.append(box)
        else:
            print(f"    ✂️ [拦截] 发现超大打包框 (面积占比 {area_ratio*100:.1f}%)，已斩杀！")

    # ================= 🧼 清洗第三步：语义隔离防误杀 =================
    safe_targets = []
    for box in area_filtered_targets:
        is_misidentified = False
        for neg_box in negatives:
            if compute_iou(box, neg_box) > NEG_IOU_THRESH:
                is_misidentified = True
                print(f"    ✂️ [拦截] 发现误杀框 (与吊灯/壁炉高度重合)，已斩杀！")
                break
        if not is_misidentified:
            safe_targets.append(box)

    # ================= 🧼 清洗第四步：NMS 消除重复与截断重叠 =================
    final_targets = []
    for box in safe_targets:
        is_duplicate = False
        for valid_box in final_targets:
            if compute_iou(box, valid_box) > NMS_IOU_THRESH:
                is_duplicate = True
                print(f"    ✂️ [拦截] 发现局部重复/重叠框，已自动融合擦除！")
                break
        if not is_duplicate:
            final_targets.append(box)

    # ================= 📝 保存标准 YOLO 标签 =================
    if not final_targets:
        print(f"  [空] 所有候选框均被判定为废框，不生成标签。")
        continue

    label_filename = os.path.splitext(filename)[0] + ".txt"
    label_path = os.path.join(OUTPUT_LABEL_DIR, label_filename)
    
    with open(label_path, "w") as f:
        for box in final_targets:
            x_min, y_min, x_max, y_max = box
            
            # 转换为 YOLO 格式 (中心点, 宽高, 归一化)
            cx = ((x_min + x_max) / 2.0) / w_img
            cy = ((y_min + y_max) / 2.0) / h_img
            box_w = (x_max - x_min) / w_img
            box_h = (y_max - y_min) / h_img
            
            # 防越界保护
            cx, cy = max(0, min(cx, 1)), max(0, min(cy, 1))
            box_w, box_h = max(0, min(box_w, 1)), max(0, min(box_h, 1))
            
            f.write(f"{CLASS_ID} {cx:.6f} {cy:.6f} {box_w:.6f} {box_h:.6f}\n")
            
    print(f"  ✅ [成功] 经过重重过滤，保留 {len(final_targets)} 个纯净横梁框，已保存！")