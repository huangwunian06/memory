"""
批量添加班级花名册
运行：python add_roster.py
"""
import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'highschool_memories.settings')
sys.path.insert(0, os.path.dirname(__file__))

import django
django.setup()

from memories.models import PendingRegistration

# 从微信群接龙提取的名单（共 53 人，李羿、岳开盛已在列表中但可重复运行无影响）
NAMES = [
    '张齐贤', '么甲烨', '马飞越', '闫雨桐', '郭勇志',
    '乔金萱', '许有赛', '钱耀瑞', '邢佑仪', '白雨彤',
    '张可欣', '宋晓影', '高乙博', '高学烨', '李奥',
    '郭爽', '王亚涵', '倪志坤', '徐紫萌', '李依泽',
    '姜新茹', '刘一', '杜欣', '安荣飞', '赵新城',
    '温建航', '程学尚', '李瑞豪', '李智星', '赵雨嘉',
    '刘欣悦', '徐鑫楠', '柳尚航', '闫祎然', '孙继文',
    '吴洪越', '段奥慧', '尚子凡', '任建彬', '刘贝贝',
    '周凯博', '王倩倩', '王亦菲', '李学达', '彭丁昊',
    '王晓雅', '许占旭', '丁安乐', '乔嘉柯', '李羿',
    '鲁孔宇', '范海涛', '岳开盛','杨萨迪',
]

added = 0
skipped = 0
for name in NAMES:
    name = name.strip()
    if not name:
        continue
    _, created = PendingRegistration.objects.get_or_create(name=name)
    if created:
        print(f'  ✅ 已添加: {name}')
        added += 1
    else:
        print(f'  ⏭️  已存在: {name}')
        skipped += 1

print(f'\n完成：新增 {added} 人，跳过 {skipped} 人')
print(f'花名册当前共 {PendingRegistration.objects.count()} 人')
