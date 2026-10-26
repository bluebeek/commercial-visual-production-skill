#!/usr/bin/env python3
"""Compile scoped prompt contracts from a grounded blueprint (no calls to image generation APIs)."""
import argparse,sys,json,re
from pathlib import Path
from _common import load_project,validate_project

def fmtbox(box):
    x,y,w,h=box
    return f"left={x:.3f}, top={y:.3f}, width={w:.3f}, height={h:.3f} (normalized 0..1)"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--spec',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    project,root=load_project(args.spec)
    report,_=validate_project(project,root)
    if report['status']=='BLOCK': ap.error('invalid blueprint: '+'; '.join(report['errors']))
    args.out.mkdir(parents=True,exist_ok=True)
    direction=project.get('creative_direction','Follow provided composition blueprint; no additional assumptions about brand')
    bans=project.get('forbidden_elements',[])
    positives=project.get('style_rules',[])
    elements=project['elements']
    not_ai=[]
    ai_elements=[]
    for e in elements:
        role=e.get('role'); lock=e.get('lock','L3')
        if role in ('person','coach','product','logo','architecture','headline','subhead','text') or lock in ('L0','L1'):
            not_ai.append(e)
        elif role in ('background','decoration') and lock in ('L2','L3'):
            ai_elements.append(e)
    lines=[
        '【内置 image_gen.imagegen / 靶向生成合同 — 正式受控生产时使用蓝图草图作为布局参考】',
        '实际AI生成只调用 image_gen.imagegen；不切换连接器、CLI/API或其他模型。当前内置接口无model参数，不能从此合同核实后台Image 2.5版本。',
        '保留原生产步骤；按工序允许分素材生成、候选迭代和返工，不限制单张成片的生成调用次数。',
        '本次只生成【背景和允许的辅助视觉】，禁止尝试生成最终人物、产品包装、Logo、赛事文案。',
        '画布尺寸: '+str(project['canvas']['width'])+' × '+str(project['canvas']['height']),
        '背景主色(最终仍需软件采样验证): '+project['canvas'].get('background','#FFFFFF'),
        '艺术方向（项目输入）: '+str(direction),
        '正向风格规则: '+('；'.join(map(str,positives)) if positives else '仅遵循已有参考/蓝图，不自拟风格'),
        '明确禁令: '+('；'.join(map(str,bans)) if bans else '不要额外增加未列明主体、品牌文字或装饰'),
        '留白和视觉限制:',
    ]
    for e in elements:
        if e.get('role')=='negative_space': lines.append(' - 空白预留 '+e['id']+': '+fmtbox(e['box'])+'；不要填满此区。')
    lines.append('以下对象只表示占位范围，不应被模型重绘:')
    for e in not_ai:
        lines.append(' - '+e['id']+' ['+str(e.get('role'))+']: '+fmtbox(e['box'])+'；用真实素材/可编辑文字后期合成。')
    lines.append('允许AI设计的对象（除非用户另有授权，不要扩展）:')
    for e in ai_elements:
        lines.append(' - '+e['id']+' ['+e.get('role','')+']: '+fmtbox(e['box'])+'；'+str(e.get('visual_spec','依据蓝图保持克制')))
    if not ai_elements:
        lines.append(' - 未定义单独的AI辅助元素；只输出简洁背景，不凭空添加图案。')
    lines.extend([
        '注意：坐标是描述性定位引导，不等于生成模型能精确按像素放置；最终必须回到蓝图/图层进行校正。',
        '先生成无人物、无包装、无品牌Logo、无最终文字的背景版本，确认后再通过确定性合成放入真实素材。',
    ])
    (args.out/'01_background_prompt.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    edit_lines=['【局部修改执行约束】','修改必须基于最后一次已批准的母版。','将 mask_editable.png 作为修改区参考。','其余不变的承诺只是一项意图，不是技术性像素锁。','生成新图后使用 locked_edit.py 将候选图限制在编辑区；检查接缝。', '严格尺寸一致，禁止默默缩放/旋转/裁切候选图。']
    for r in project.get('editable_regions',[]): edit_lines.append('编辑区: '+r['id']+': '+str(r.get('rect',r.get('polygon'))))
    for r in project.get('protected_regions',[]): edit_lines.append('锁定区: '+r['id']+': '+str(r.get('rect',r.get('polygon'))))
    (args.out/'02_local_edit_contract.txt').write_text('\n'.join(edit_lines)+'\n',encoding='utf-8')
    protected=['【必须使用原始素材/设计软件执行的对象】']
    for e in not_ai:
        protected.append(f"- {e['id']} | {e.get('role')} | {e.get('lock','L3')} | {e.get('source','SOURCE_MISSING')} | {fmtbox(e['box'])}")
    protected.append('核心人物身份、包装标识、真实场馆与正式文字必须对照官方素材/文字逐项验证。')
    (args.out/'03_original_asset_contract.txt').write_text('\n'.join(protected)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','files':[p.name for p in sorted(args.out.glob('*.txt'))],'ai_elements':[e['id'] for e in ai_elements], 'original_asset_elements':[e['id'] for e in not_ai]},ensure_ascii=False,indent=2))
    return 0
if __name__=='__main__':sys.exit(main())
