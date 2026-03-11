import os
import itertools

# ================= 1. 核心配置区 =================
LABEL_DIR = "A2_lable"          # 原始标签文件夹
OUTPUT_DIR = "A2_new_clean"   # 清洗后标签保存文件夹

# 针对电商图放宽面积限制
MIN_AREA = 0.01        # 最小面积 1% (太小纯噪点)
MAX_AREA = 0.95        # 最大面积 95% (电商图特写允许占满全屏)

# 🌟 你的核心灵感：互斥与相似度判定
DISJOINT_IOU = 0.1     # 两个框IoU小于10%，认为是不重合的两个实体
SIMILAR_AREA_RATIO = 0.4 # 两个实体面积比例大于0.4，认为是两个“同级”的椅子，而不是“椅子和轮子”

# 包含判定
IOA_THRESH = 0.85      # 小框有85%的面积在大框里，认为是包含关系
NMS_IOU = 0.70         # 两个框重叠度高达70%，认为是画重复了
# ============================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

def compute_boxes_relation(box1, box2):
    """计算两个框的 IoU 和互相的包含比例 IoA"""
    x1_min, y1_min, x1_max, y1_max = box1['coords']
    x2_min, y2_min, x2_max, y2_max = box2['coords']

    inter_x_min, inter_y_min = max(x1_min, x2_min), max(y1_min, y2_min)
    inter_x_max, inter_y_max = min(x1_max, x2_max), min(y1_max, y2_max)
    
    inter_w = max(0, inter_x_max - inter_x_min)
    inter_h = max(0, inter_y_max - inter_y_min)
    inter_area = inter_w * inter_h
    
    area1, area2 = box1['area'], box2['area']
    
    iou = inter_area / (area1 + area2 - inter_area) if (area1 + area2 - inter_area) > 0 else 0
    ioa1 = inter_area / area1 if area1 > 0 else 0 # 框1被框2包含的比例
    ioa2 = inter_area / area2 if area2 > 0 else 0 # 框2被框1包含的比例
    
    return iou, ioa1, ioa2

print("🚀 启动 4.0 电商图专属清洗机 (基于拓扑互斥逻辑)...")
stats = {"processed": 0, "group": 0, "parts": 0, "duplicates": 0}

for filename in os.listdir(LABEL_DIR):
    if not filename.endswith('.txt'): continue
    
    filepath = os.path.join(LABEL_DIR, filename)
    with open(filepath, 'r') as f:
        lines = f.readlines()
        
    boxes = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) != 5: continue
        
        cx, cy, w, h = map(float, parts[1:])
        area = w * h
        if area < MIN_AREA or area > MAX_AREA:
            continue
            
        coords = [cx - w/2, cy - h/2, cx + w/2, cy + h/2]
        boxes.append({'line': line, 'coords': coords, 'area': area, 'status': 'keep'})
        
    # --- 🔪 战术一：根据你的灵感，揪出并斩杀“打包框” ---
    # 如果大框 A 同时包含 小框 B 和 小框 C
    # 并且 B 和 C 大小接近，且不重合，那么 A 就是非法的打包框！
    for i in range(len(boxes)):
        big = boxes[i]
        
        # 找出所有被 big 包含的小框
        contained_boxes = []
        for j in range(len(boxes)):
            if i == j: continue
            small = boxes[j]
            if big['area'] > small['area']:
                _, _, ioa_small = compute_boxes_relation(big, small)
                if ioa_small > IOA_THRESH:
                    contained_boxes.append(small)
        
        # 检查被包含的小框中，是否有两个互斥且相似的实体
        is_group_box = False
        for b1, b2 in itertools.combinations(contained_boxes, 2):
            iou_b1_b2, _, _ = compute_boxes_relation(b1, b2)
            area_ratio = min(b1['area'], b2['area']) / max(b1['area'], b2['area'])
            
            # 核心判断：如果它俩几乎不挨着，且面积相差不大
            if iou_b1_b2 < DISJOINT_IOU and area_ratio > SIMILAR_AREA_RATIO:
                is_group_box = True
                break
                
        if is_group_box:
            big['status'] = 'group_box'
            stats["group"] += 1

    # 清理掉打包框，只留正常框进行下一步
    survivors = [b for b in boxes if b['status'] == 'keep']
    
    # --- 🔪 战术二：大框吃小框 (清除局部轮子/坐垫) ---
    survivors.sort(key=lambda x: x['area'], reverse=True) # 面积从大到小排
    
    for i in range(len(survivors)):
        if survivors[i]['status'] != 'keep': continue
        
        for j in range(i + 1, len(survivors)):
            if survivors[j]['status'] != 'keep': continue
            
            iou, ioa_big, ioa_small = compute_boxes_relation(survivors[i], survivors[j])
            
            # 情况A：小框被大框完全包裹 -> 小框是零件，杀！
            if ioa_small > IOA_THRESH:
                survivors[j]['status'] = 'part_box'
                stats["parts"] += 1
            # 情况B：两个框高度重合 -> 画重复了，杀小框！
            elif iou > NMS_IOU:
                survivors[j]['status'] = 'duplicate_box'
                stats["duplicates"] += 1

    # --- 💾 保存最终极其纯净的框 ---
    final_boxes = [b for b in survivors if b['status'] == 'keep']
    if final_boxes:
        with open(os.path.join(OUTPUT_DIR, filename), 'w') as f:
            for b in final_boxes:
                f.write(b['line'])
                
    stats["processed"] += 1

print("\n🎉 针对电商图清洗完成！你的逻辑完美生效！战报：")
print(f"📄 处理图片数: {stats['processed']}")
print(f"🗑️ 斩杀 [打包框(一框多椅)]: {stats['group']} 个")
print(f"🧩 斩杀 [局部零件(坐垫/轮子)]: {stats['parts']} 个")
print(f"✂️ 斩杀 [重复多余框]: {stats['duplicates']} 个")
print(f"👉 干净如洗的标签已存入: {OUTPUT_DIR}")