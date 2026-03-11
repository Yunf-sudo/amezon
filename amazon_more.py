import os
import torch
import shutil
from PIL import Image
from tqdm import tqdm
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

# ==================== 🎯 核心配置区 ====================
# 您刚爬取并清洗完毕的原始图片文件夹
SOURCE_DATASET_DIR = "B"

# 脚本将自动生成的、专供 RT-DETR 训练的标准数据集目录
OUTPUT_DATASET_DIR = "RTDETR_Beams_Dataset"

# 文本提示词 (Prompt)：告诉大模型你要框什么
# 多个特征用英文句号隔开。我们统一定义它们为 class_id = 0 (横梁)
# TEXT_PROMPT = "exposed ceiling beam. wooden beam. steel ceiling beam."
TEXT_PROMPT = "beam . ceiling beam ."

# 阈值设置 (0~1 之间)
# 阈值太低会把门框当横梁，阈值太高会漏掉暗处的横梁，0.3 是个很好的起点
BOX_THRESHOLD = 0.15
TEXT_THRESHOLD = 0.15
# =======================================================

def setup_directories():
    """创建标准 YOLO/RT-DETR 数据集目录结构"""
    images_dir = os.path.join(OUTPUT_DATASET_DIR, "images", "train")
    labels_dir = os.path.join(OUTPUT_DATASET_DIR, "labels", "train")
    
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)
    return images_dir, labels_dir

def generate_yaml():
    """自动生成供 RT-DETR 训练使用的 data.yaml 配置文件"""
    yaml_content = f"""
path: ./  # 数据集根目录
train: images/train
val: images/train  # 演示用，暂用训练集兼当验证集，正式训练前可自行划分 10% 到 val 文件夹

# 类别信息
nc: 1
names:
  0: beam
"""
    yaml_path = os.path.join(OUTPUT_DATASET_DIR, "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content.strip())
    print(f"📄 已生成训练配置文件: {yaml_path}")

def convert_to_yolo_format(box, img_width, img_height):
    """将 Grounding DINO 的绝对坐标 [xmin, ymin, xmax, ymax] 转换为 YOLO 归一化坐标"""
    xmin, ymin, xmax, ymax = box
    
    # 计算中心点和宽高
    x_center = (xmin + xmax) / 2.0
    y_center = (ymin + ymax) / 2.0
    width = xmax - xmin
    height = ymax - ymin
    
    # 归一化 (除以图片的宽高)
    x_center /= img_width
    y_center /= img_height
    width /= img_width
    height /= img_height
    
    # 确保数值不越界 (限制在 0.0 到 1.0 之间)
    x_center = max(0.0, min(1.0, x_center))
    y_center = max(0.0, min(1.0, y_center))
    width = max(0.0, min(1.0, width))
    height = max(0.0, min(1.0, height))
    
    return x_center, y_center, width, height

def main():
    images_train_dir, labels_train_dir = setup_directories()
    generate_yaml()
    
    # 1. 加载大模型 (自动使用 GPU 进行推理，极大地加速标注过程)
    # device = "cuda" if torch.cuda.is_available() else "cpu"
    device ="cpu"
    print(f"🤖 正在加载 Grounding DINO 模型 (计算设备: {device})... 首次运行需下载模型权重。")
    
    model_id = "IDEA-Research/grounding-dino-base"
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)
    
    # 2. 收集所有图片路径
    all_image_paths = []
    for root, _, files in os.walk(SOURCE_DATASET_DIR):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                all_image_paths.append(os.path.join(root, file))
                
    print(f"📦 扫描完毕，共发现 {len(all_image_paths)} 张待标注图片，启动自动化流水线！")

    # 3. 遍历图片进行自动化推理
    for img_path in tqdm(all_image_paths, desc="Auto-Labeling Progress"):
        try:
            image = Image.open(img_path).convert("RGB")
            img_width, img_height = image.size
            
            # 预处理输入
            inputs = processor(images=image, text=TEXT_PROMPT, return_tensors="pt").to(device)
            
            # 模型推理
            with torch.no_grad():
                outputs = model(**inputs)
            
            # 后处理：提取边界框 (只保留置信度大于设定阈值的框)
            results = processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                threshold=BOX_THRESHOLD,
                text_threshold=TEXT_THRESHOLD,
                target_sizes=[image.size[::-1]]
            )[0]
            
            boxes = results["boxes"].cpu().numpy()
            scores = results["scores"].cpu().numpy()
            
            if len(scores) > 0:
                            print(f"[{base_name}] 找到目标! 最高得分: {max(scores):.3f}")
            else:
                            print(f"[{base_name}] 模型得分低于 0.15，啥也没看见...")

            # 只有当模型在图里发现了至少一个横梁，我们才把它加入训练集！
            # 这能自动剔除那些完全没有横梁的废图，提高数据集纯度
            if len(boxes) > 0:
                base_name = os.path.splitext(os.path.basename(img_path))[0]
                
                # 拷贝图片到标准目录
                new_img_path = os.path.join(images_train_dir, f"{base_name}.jpg")
                shutil.copy2(img_path, new_img_path)
                
                # 写入 YOLO 格式的 txt 标注文件
                txt_path = os.path.join(labels_train_dir, f"{base_name}.txt")
                with open(txt_path, "w", encoding="utf-8") as f:
                    for box, score in zip(boxes, scores):
                        x_c, y_c, w, h = convert_to_yolo_format(box, img_width, img_height)
                        # 类别 ID 统一为 0 (代表横梁)，保留 6 位小数
                        f.write(f"0 {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}\n")
                        
        except Exception as e:
            print(f"\n[!] 处理图片失败跳过: {img_path} | 错误: {e}")

    print("\n🎉 自动化标注圆满完成！")
    print(f"🚀 数据集已重构完毕，存放在: {OUTPUT_DATASET_DIR}")
    print("您可以直接将该目录丢给 RT-DETR 启动训练了！")

if __name__ == "__main__":
    main()