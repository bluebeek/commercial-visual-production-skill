#!/usr/bin/env python3
"""Quantify aligned image changes for commercial visual QC (no semantic judgment)."""
import argparse
import json
from pathlib import Path
from _compact import emit_result
from PIL import Image, ImageDraw
import numpy as np


def image_rgb(path):
    with Image.open(path) as source:
        rgba = source.convert('RGBA')
        canvas = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
        canvas.alpha_composite(rgba)
        return np.asarray(canvas.convert('RGB'), dtype=np.uint8)


def build_mask(spec, image_size, coordinates):
    w, h = image_size
    mask = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(mask)
    scale_x, scale_y = (w, h) if coordinates == 'normalized' else (1, 1)
    if 'rect' in spec:
        points = spec['rect']
        if not isinstance(points, list) or len(points) != 4:
            raise ValueError(f"invalid rectangle for {spec.get('id', '?')}")
        x0, y0, x1, y1 = map(float, points)
        if x0 >= x1 or y0 >= y1:
            raise ValueError(f"rectangle should have positive area for {spec.get('id', '?')}")
        polygon = [(x0 * scale_x, y0 * scale_y), (x1 * scale_x, y0 * scale_y),
                   (x1 * scale_x, y1 * scale_y), (x0 * scale_x, y1 * scale_y)]
    elif 'polygon' in spec:
        points = spec['polygon']
        if not isinstance(points, list) or len(points) < 3 or any(len(x) != 2 for x in points):
            raise ValueError(f"invalid polygon for {spec.get('id', '?')}")
        polygon = [(float(x) * scale_x, float(y) * scale_y) for x, y in points]
    else:
        raise ValueError(f"region {spec.get('id','?')} has no rect or polygon")
    if coordinates == 'normalized' and any(not (0 <= a <= 1) for p in (spec.get('polygon') or [spec['rect'][:2],spec['rect'][2:]]) for a in p):
        raise ValueError(f"out-of-range normalized coordinate for {spec.get('id','?')}")
    draw.polygon(polygon, fill=255)
    result = np.asarray(mask) > 0
    if not np.any(result):
        raise ValueError(f"empty region: {spec.get('id','?')}")
    return result


def stats(data, changed, region_mask):
    values = data[region_mask]
    n = int(values.size)
    return {
        'pixels': n,
        'changed_pixels': int(np.count_nonzero(changed & region_mask)),
        'changed_fraction': round(float(np.count_nonzero(changed & region_mask) / n), 8),
        'mean_max_channel_delta': round(float(np.mean(values)), 3),
        'p95_max_channel_delta': round(float(np.percentile(values, 95)), 3)
    }


def main():
    parser = argparse.ArgumentParser(description='Aligned-image difference measurement; NOT a design-quality verdict')
    parser.add_argument('baseline', type=Path)
    parser.add_argument('revised', type=Path)
    parser.add_argument('--regions', type=Path, help='JSON with coordinate_system, locked_regions and editable_regions')
    parser.add_argument('--tolerance', type=int, default=5, help='Changed if max RGB-channel absolute delta > tolerance (0-255)')
    parser.add_argument('--out', type=Path, default=Path('qc-output'))
    parser.add_argument('--full-output',action='store_true')
    args = parser.parse_args()
    if not 0 <= args.tolerance <= 255:
        parser.error('--tolerance must be within 0..255')
    before, after = image_rgb(args.baseline), image_rgb(args.revised)
    if before.shape != after.shape:
        parser.error(f'Images must be identical size; got {before.shape[:2]} and {after.shape[:2]}. No auto-resize.')
    height, width = before.shape[:2]
    delta = np.max(np.abs(before.astype(np.int16) - after.astype(np.int16)), axis=2).astype(np.uint8)
    changed = delta > args.tolerance
    everything = np.ones((height, width), dtype=bool)
    report = {
        'baseline': args.baseline.name,
        'revised': args.revised.name,
        'image_dimensions': {'width': width, 'height': height},
        'tolerance_per_rgb_channel': args.tolerance,
        'judgment': 'No automatic PASS/FAIL: compare regions, assets, text, and brief manually.',
        'global': stats(delta, changed, everything),
        'regions': []
    }
    if args.regions:
        config = json.loads(args.regions.read_text(encoding='utf8'))
        coordinate_system = config.get('coordinate_system', 'normalized')
        if coordinate_system not in ('normalized','pixel'):
            parser.error('coordinate_system must be normalized or pixel')
        locked_union = np.zeros((height,width), dtype=bool)
        editable_union = np.zeros((height,width), dtype=bool)
        for key, kind in [('locked_regions','locked'),('editable_regions','editable')]:
            for index, spec in enumerate(config.get(key, [])):
                region = build_mask(spec, (width,height), coordinate_system)
                (locked_union if kind == 'locked' else editable_union)[:] |= region
                report['regions'].append({'id': str(spec.get('id', f'{kind}_{index+1}')),
                                          'kind': kind, **stats(delta, changed, region)})
        overlap = int(np.count_nonzero(locked_union & editable_union))
        report['locked_editable_overlap_pixels'] = overlap
        if overlap > 0:
            report['region_warning'] = 'Locked and editable masks overlap; revise regions before interpreting.'
        if np.any(locked_union):
            report['locked_union'] = stats(delta, changed, locked_union)
        if np.any(editable_union):
            report['editable_union'] = stats(delta, changed, editable_union)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/'metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    # Visual aids: scaled delta and a red overlay, not a semantic error map.
    Image.fromarray(delta).save(args.out/'diff.png')
    overlay = after.copy()
    overlay[changed] = (0.55 * overlay[changed] + 0.45 * np.array([255, 25, 25])).astype(np.uint8)
    Image.fromarray(overlay).save(args.out/'changed_overlay.png')
    emit_result(report,args.out/'metrics.json',args.full_output)


if __name__ == '__main__':
    main()
