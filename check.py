import os
import cv2

# ==== 配置区 (检查路径是否正确) ====
IMAGE_DIR = "mirror"        # 你的原图文件夹
LABEL_DIR = "mirror_label"        # 你的txt矩形框标签文件夹
OUTPUT_DIR = "mirror_check"      # 预览图保存的文件夹（自动创建）
# ================================

os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"正在跑专用矩形框预览脚本...")

for txt_filename in os.listdir(LABEL_DIR):
    if not txt_filename.endswith(".txt"):
        continue
    
    # 找到对应的图片
    img_filename = txt_filename.replace(".txt", ".jpg") 
    img_path = os.path.join(IMAGE_DIR, img_filename)
    label_path = os.path.join(LABEL_DIR, txt_filename)
    
    if not os.path.exists(img_path):
        continue
        
    # 读取图片和宽高
    img = cv2.imread(img_path)
    if img is None:
        continue
    h_img, w_img, _ = img.shape
    
    # 读取 txt 文件里的标准 YOLO 框数据
    with open(label_path, "r") as f:
        lines = f.readlines()
        
    for line in lines:
        parts = line.strip().split()
        if len(parts) != 5: # 确保它是标准的5个值 (class_id, cx, cy, w, h)
            print(f"  [警告] 标签文件格式异常，跳过: {txt_filename}")
            continue
            
        class_id = int(parts[0])
        # 中心点坐标 (归一化)
        cx = float(parts[1])
        cy = float(parts[2])
        # 框宽高 (归一化)
        box_w = float(parts[3])
        box_h = float(parts[4])

        # 1. 计算左上角和右下角的像素坐标 (x1, y1, x2, y2)
        x1 = int((cx - box_w / 2) * w_img)
        y1 = int((cy - box_h / 2) * h_img)
        x2 = int((cx + box_w / 2) * w_img)
        y2 = int((cy + box_h / 2) * h_img)
        
        # 2. 限制边界，防止框画到图片外面去
        x1, y1 = max(0, min(x1, w_img)), max(0, min(y1, h_img))
        x2, y2 = max(0, min(x2, w_img)), max(0, min(y2, h_img))
        
        # 3. 在原图上画出绿色的矩形检测框 (线宽为 3)
        cv2.rectangle(img, (x1, y1), (x2, y2), color=(0, 255, 0), thickness=3)
        
    # 保存预览图
    out_path = os.path.join(OUTPUT_DIR, img_filename)
    cv2.imwrite(out_path, img)

print(f"\n✅ 全部预览图生成完毕，快去 {OUTPUT_DIR} 文件夹看看吧！这一次绝对是框了！")