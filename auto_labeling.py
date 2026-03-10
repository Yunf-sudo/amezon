import os
import warnings

# 1. 强制禁用损坏的 xformers 加速器，防止输出脏数据（关键！）
os.environ["XFORMERS_DISABLED"] = "1"
# 2. 忽略烦人的警告
warnings.filterwarnings("ignore")

import cv2
import torch
import numpy as np
from PIL import Image
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
from segment_anything import build_sam, SamPredictor

# ================= 1. 配置区 =================
IMAGE_DIR = "Ayugang"          # 你的图片文件夹
# IMAGE_DIR = "Acabinet"          # 你的图片文件夹
# OUTPUT_LABEL_DIR = "A2_lable"   # 生成的 YOLO 标签保存路径
OUTPUT_LABEL_DIR = "A13_lable"   # 生成的 YOLO 
# TEXT_PROMPT = "potted plant . houseplant . artificial plant . shrub . bush . fern . pine tree . monstera . succulent . bamboo ."  # 植物
# TEXT_PROMPT = "mirror . wall mirror . floor mirror . full-length mirror . vanity mirror . mirror frame ." # 镜子
# TEXT_PROMPT = "bed . bed frame . bunk bed . canopy bed . sofa bed . daybed . folding bed . murphy bed . sleeping furniture ."
# TEXT_PROMPT = "chair . seat . seating furniture . office chair . dining chair . gaming chair . armchair . lounge chair . bar stool . folding chair . rocking chair . recliner . desk chair . swivel chair . bean bag chair . wooden chair . plastic chair . metal chair . leather chair . chair with wheels . four-legged chair . high back chair . stool . seating ."
# TEXT_PROMPT = "wooden cabinet . wardrobe . dresser . tv stand . bookcase . cupboard . sideboard . shoe cabinet . nightstand . storage furniture ."
# TEXT_PROMPT = "gas stove . cooktop . gas range . electric stove . induction cooktop . oven . built-in oven . wall oven . microwave . microwave oven . over-the-range microwave . range hood . kitchen appliances ."
# TEXT_PROMPT = "door . front door . wooden door . bedroom door . interior door . sliding door . sliding glass door . french doors . barn door . pocket door . hidden door . door frame . open door . closed door ."
# TEXT_PROMPT = "lamp . light fixture . chandelier . pendant light . ceiling light . floor lamp . standing lamp . table lamp . desk lamp . wall sconce . bedside lamp . lighting ."
# TEXT_PROMPT = "mirror . wall mirror . floor mirror . full-length mirror . bathroom vanity mirror . round mirror . framed mirror . reflective glass . vanity mirror ."
# TEXT_PROMPT = "plant . potted plant . houseplant . indoor plant . artificial plant . large floor plant . tree in pot . small desk plant . hanging plant . vase with flowers . fern . monstera . bonsai . succulent ."
# TEXT_PROMPT = "bathtub . freestanding tub . bath tub . clawfoot tub . acrylic bathtub . alcove tub . shower . shower enclosure . glass shower door . walk-in shower . shower head . shower system ."
# TEXT_PROMPT = "table . dining table . coffee table . center table . side table . end table . desk . office desk . computer desk . console table . wooden table . glass table ."
# TEXT_PROMPT = "toilet . commode . water closet . toilet bowl . smart toilet . wall hung toilet . one piece toilet ."
# TEXT_PROMPT = "window . glass window . window frame . sliding window . floor to ceiling window . large panoramic window . window blinds . window with curtains . casement window ."
# TEXT_PROMPT = "bathroom vanity . bathroom sink . washbasin . pedestal sink . vanity cabinet . sink basin . double vanity . floating vanity ."
# 涵盖：统称 + 独立式 + 嵌入式 + 特殊形态（如复古爪脚、按摩浴缸）
TEXT_PROMPT = "bathtub . bath tub . freestanding tub . clawfoot tub . soaking tub . alcove bathtub . acrylic bathtub . hot tub . jacuzzi . wash tub ."

BOX_THRESHOLD = 0.4             # 框置信度
TEXT_THRESHOLD = 0.41             # 文本匹配度
CLASS_ID = 13                      # YOLO 类别 ID

SAM_WEIGHTS = "weights/sam_vit_h_4b8939.pth" # 之前下载的 SAM 权重保持不变
# ============================================

os.makedirs(OUTPUT_LABEL_DIR, exist_ok=True)
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"正在使用 {device.upper()} 模式运行...")
print("正在加载纯 Python 版 GroundingDINO 和 SAM，请稍候...")

# 1. 加载 HuggingFace 版的 GroundingDINO (它会自动下载并缓存轻量级权重，不会报 _C 错误)
# 1. 【离线模式】直接从本地文件夹加载 GroundingDINO
processor = AutoProcessor.from_pretrained("./local_gd_model/processor", local_files_only=True)
gd_model = AutoModelForZeroShotObjectDetection.from_pretrained(
    "./local_gd_model/model",
    attn_implementation="eager",
    local_files_only=True  # 👈 这个参数是关键！强迫它不准联网找，只读本地！
).to(device)
# 2. 加载本地的 SAM
sam_predictor = SamPredictor(build_sam(checkpoint=SAM_WEIGHTS).to(device))
print("模型加载完成！开始自动化标注...")

for filename in os.listdir(IMAGE_DIR):
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        continue
    
    image_path = os.path.join(IMAGE_DIR, filename)
    print(f"\n---> 正在处理: {filename}")
    
# 替换后的代码：加入 try-except 保护罩
    try:
        image = Image.open(image_path).convert("RGB")
        image_np = np.array(image)
    except Exception as e:
        print(f"  ⚠️ [警告] 图片严重损坏或无法读取，已自动跳过: {filename} (原因: {e})")
        continue  # 直接跳过这张坏图，继续处理下一张！
    # 【第一阶段】：GroundingDINO 检测
    inputs = processor(images=image, text=TEXT_PROMPT, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = gd_model(**inputs)

    # 解析结果 (直接输出绝对坐标 x1, y1, x2, y2，省去了原版复杂的转换)
    target_sizes = torch.tensor([image.size[::-1]]) # 获取宽高
    results = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=BOX_THRESHOLD,
        text_threshold=TEXT_THRESHOLD,
        target_sizes=target_sizes
    )[0]

    boxes_abs = results["boxes"]
    
    if boxes_abs.shape[0] == 0:
        print(f"  [跳过] 未检测到 '{TEXT_PROMPT}'")
        continue

# ... 前面的代码保持不变 (读图、GroundingDINO检测) ...
    
    # 提取绝对坐标框 [x_min, y_min, x_max, y_max]
    boxes_abs = results["boxes"]
    
    if boxes_abs.shape[0] == 0:
        print(f"  [跳过] 未检测到 '{TEXT_PROMPT}'")
        continue

    # ================= 替换从这里开始 =================
    
    # 【直接生成 RT-DETR 需要的标准 YOLO 检测框格式】
    label_filename = os.path.splitext(filename)[0] + ".txt"
    label_path = os.path.join(OUTPUT_LABEL_DIR, label_filename)
    h_img, w_img, _ = image_np.shape
    
    with open(label_path, "w") as f:
        for box in boxes_abs:
            x_min, y_min, x_max, y_max = box.tolist()
            
            # 1. 计算框的中心点坐标 (cx, cy) 和 宽高 (w, h)
            cx = (x_min + x_max) / 2.0
            cy = (y_min + y_max) / 2.0
            box_w = x_max - x_min
            box_h = y_max - y_min
            
            # 2. 归一化处理 (将像素值除以图片的真实宽高，变成 0~1 之间的小数)
            cx /= w_img
            cy /= h_img
            box_w /= w_img
            box_h /= h_img
            
            # 3. 限制数值不要越界 (极少数情况下由于精度问题可能超出1.0)
            cx, cy = max(0, min(cx, 1)), max(0, min(cy, 1))
            box_w, box_h = max(0, min(box_w, 1)), max(0, min(box_h, 1))
            
            # 4. 写入标准 YOLO 检测框格式
            line = f"{CLASS_ID} {cx:.6f} {cy:.6f} {box_w:.6f} {box_h:.6f}\n"
            f.write(line)
            
    print(f"  [成功] 提取了 {boxes_abs.shape[0]} 个 RT-DETR 检测框，已保存为 {label_filename}")