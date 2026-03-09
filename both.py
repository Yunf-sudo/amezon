import os
import shutil

# ==================== 配置区 ====================
# 你的两个源文件夹名称
SOURCE_FOLDERS = ["private_cabinet", "public_cabinet"]  
# 合并后的目标文件夹名称
TARGET_FOLDER = "Acabinet"                       
# ================================================

# 1. 创建目标文件夹（如果不存在会自动创建）
os.makedirs(TARGET_FOLDER, exist_ok=True)

# 定义支持的图片格式，防止把其他杂乱文件混进去
valid_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')

# 计数器
count = 1

print(f"🚀 开始合并数据到 '{TARGET_FOLDER}' 文件夹...")

for folder in SOURCE_FOLDERS:
    # 检查文件夹是否存在
    if not os.path.exists(folder):
        print(f"  -> ⚠️ 警告：找不到文件夹 '{folder}'，已跳过。")
        continue
        
    print(f"\n📂 正在处理文件夹: {folder}")
    
    for filename in os.listdir(folder):
        # 检查后缀名
        ext = os.path.splitext(filename)[1].lower()
        if ext not in valid_extensions:
            continue
            
        # 2. 生成新文件名 (例如: 00001mirror.jpg)
        # {count:05d} 的意思是把数字补齐为 5 位数，前面自动补 0
        new_filename = f"{count:05d}cabinet{ext}"
        
        # 构建完整路径
        src_path = os.path.join(folder, filename)
        dst_path = os.path.join(TARGET_FOLDER, new_filename)
        
        # 3. 执行复制 (用 shutil.copy2 可以保留原始图片的创建时间等属性)
        try:
            shutil.copy2(src_path, dst_path)
            count += 1
        except Exception as e:
            print(f"  -> ❌ 复制文件 {filename} 时出错: {e}")

print(f"\n✅ 合并大功告成！总共成功重命名并转移了 {count - 1} 张图片！")
print(f"📁 快去 '{TARGET_FOLDER}' 文件夹里检阅你的千军万马吧！")