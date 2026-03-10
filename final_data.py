import os
import shutil
import random
import yaml

# ================= 1. 极其重要的配置区 =================
# ⚠️ 请仔细核对：类别ID -> 图片文件夹、标签文件夹、类别英文名
# 你的 TXT 标签里写的是几号，这里就把它的字典键值设为几号！
DATASET_CONFIG = {
    0: {"img_dir": "Abed",       "lbl_dir": "A0_lable",  "name": "bed"},
    1: {"img_dir": "Acabinet",   "lbl_dir": "A1_lable",  "name": "cabinet"},
    2: {"img_dir": "Achair",     "lbl_dir": "A2_lable",  "name": "chair"},
    3: {"img_dir": "Acook",      "lbl_dir": "A3_lable",  "name": "cook"},
    4: {"img_dir": "Adoor",      "lbl_dir": "A4_lable",  "name": "door"},
    5: {"img_dir": "Alight",     "lbl_dir": "A5_lable",  "name": "light"},
    6: {"img_dir": "Amirror",    "lbl_dir": "A6_lable",  "name": "mirror"},
    7: {"img_dir": "Aplant",     "lbl_dir": "A7_lable",  "name": "plant"},
    8: {"img_dir": "Ashower",    "lbl_dir": "A8_lable",  "name": "shower"},
    9: {"img_dir": "Atable",     "lbl_dir": "A9_lable",  "name": "table"},
    10: {"img_dir": "Atoilet",   "lbl_dir": "A10_lable", "name": "toilet"},
    11: {"img_dir": "Awindow",   "lbl_dir": "A11_lable", "name": "window"},
    12: {"img_dir": "Axishoutai", "lbl_dir": "A12_lable", "name": "vanity"}, 
    13: {"img_dir": "Ayugang",   "lbl_dir": "A13_lable", "name": "bathtub"}  
}

# 基础路径配置
BASE_DIR = "." # 你当前所在的目录
OUTPUT_DATASET_DIR = "RT_DETR_Dataset" # 最终生成的训练集文件夹名
TRAIN_RATIO = 0.8 # 80% 用于训练，20% 用于验证

# ================= 2. 创建标准 YOLO 数据集目录 =================
dirs_to_make = [
    f"{OUTPUT_DATASET_DIR}/images/train",
    f"{OUTPUT_DATASET_DIR}/images/val",
    f"{OUTPUT_DATASET_DIR}/labels/train",
    f"{OUTPUT_DATASET_DIR}/labels/val"
]
for d in dirs_to_make:
    os.makedirs(d, exist_ok=True)

# ================= 3. 开始大融合与重命名 =================
total_train = 0
total_val = 0

print("🚀 开始融合数据集，正在执行自动防重名与切割...")

for class_id, config in DATASET_CONFIG.items():
    img_dir = os.path.join(BASE_DIR, config["img_dir"])
    lbl_dir = os.path.join(BASE_DIR, config["lbl_dir"])
    class_name = config["name"]
    
    if not os.path.exists(img_dir) or not os.path.exists(lbl_dir):
        print(f"  [跳过] 找不到文件夹 {img_dir} 或 {lbl_dir}，请检查路径。")
        continue

    # 找到所有有对应 txt 标签的图片
    valid_pairs = []
    for filename in os.listdir(img_dir):
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue
            
        base_name = os.path.splitext(filename)[0]
        lbl_path = os.path.join(lbl_dir, base_name + ".txt")
        img_path = os.path.join(img_dir, filename)
        
        # 只有当对应的 txt 标签存在且不为空时，才认为它是有效数据
        if os.path.exists(lbl_path) and os.path.getsize(lbl_path) > 0:
            valid_pairs.append((img_path, lbl_path, filename))
            
    # 打乱顺序，划分训练集和验证集
    random.shuffle(valid_pairs)
    split_idx = int(len(valid_pairs) * TRAIN_RATIO)
    train_pairs = valid_pairs[:split_idx]
    val_pairs = valid_pairs[split_idx:]
    
    # 核心拷贝函数（加入分类前缀防止重名）
    def copy_files(pairs, split_type):
        count = 0
        for img_p, lbl_p, orig_filename in pairs:
            base_name, ext = os.path.splitext(orig_filename)
            # 💡 强行重命名：比如 1.jpg 变成 bed_1.jpg
            new_base_name = f"{class_name}_{base_name}"
            
            new_img_p = os.path.join(OUTPUT_DATASET_DIR, "images", split_type, new_base_name + ext)
            new_lbl_p = os.path.join(OUTPUT_DATASET_DIR, "labels", split_type, new_base_name + ".txt")
            
            shutil.copy(img_p, new_img_p)
            shutil.copy(lbl_p, new_lbl_p)
            count += 1
        return count

    # 执行拷贝
    t_count = copy_files(train_pairs, "train")
    v_count = copy_files(val_pairs, "val")
    
    total_train += t_count
    total_val += v_count
    
    print(f"  ✅ {class_name} (ID:{class_id}): 提取了 {t_count + v_count} 组有效数据 (Train:{t_count}, Val:{v_count})")

# ================= 4. 自动生成 dataset.yaml =================
yaml_path = os.path.join(OUTPUT_DATASET_DIR, "dataset.yaml")

# 提取按 ID 排序的类别名称列表
names_dict = {k: v["name"] for k, v in DATASET_CONFIG.items()}
# 确保从 0 到 13 都有，否则 RT-DETR 会报错
names_list = [names_dict.get(i, f"unknown_{i}") for i in range(max(names_dict.keys()) + 1)]

yaml_content = {
    "path": f"../{OUTPUT_DATASET_DIR}",  # 相对路径，根据你运行训练脚本的位置可能需要微调
    "train": "images/train",
    "val": "images/val",
    "names": {i: name for i, name in enumerate(names_list)}
}

with open(yaml_path, 'w', encoding='utf-8') as f:
    yaml.dump(yaml_content, f, sort_keys=False, allow_unicode=True)

print(f"\n🎉 大功告成！总计合并有效数据: {total_train + total_val} 张。")
print(f"训练集: {total_train} 张 | 验证集: {total_val} 张")
print(f"模型配置文件已生成: {yaml_path}")
print("你现在可以直接使用这个文件夹去训练 RT-DETR 了！")