"""Select a short RGB-D segment and produce one inspectable local-frame cloud."""
import argparse
from bisect import bisect_left
import hashlib
import json
from pathlib import Path
import struct
import zipfile
import zlib
import numpy as np
from packages.data.nyu_rgbd import timestamp_us,read_pnm,make_cloud,ply_bytes


def png(rgb):
    def chunk(kind,raw):
        return struct.pack('>I',len(raw))+kind+raw+struct.pack('>I',zlib.crc32(kind+raw)&0xffffffff)
    h,w=rgb.shape[:2]
    raw=b''.join(b'\0'+row.tobytes() for row in rgb)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('scene',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); root=args.output
    root.mkdir(parents=True,exist_ok=False)
    depths=sorted((timestamp_us(p.name),p) for p in args.scene.glob('d-*.pgm'))
    rgbs=sorted((timestamp_us(p.name),p) for p in args.scene.glob('r-*.ppm'))
    if not depths or not rgbs: raise ValueError('missing_images')
    times=[t for t,_ in rgbs]; start=depths[0][0]; pairs=[]
    for t,path in depths:
        if t-start>2000000: break
        pos=bisect_left(times,t)
        indices=[i for i in (pos-1,pos) if 0<=i<len(times)]
        i=min(indices,key=lambda i:(abs(times[i]-t),times[i]))
        dt=times[i]-t
        pairs.append({'depth':path.name,'rgb':rgbs[i][1].name,'depth_time_us':t,
                      'rgb_minus_depth_us':dt,'accepted':abs(dt)<=20000})
    report={'schema_version':'cospace.nyu-short-scene/0.1','scene':args.scene.name,'source_root':str(args.scene),
            'data_kind':'public_recorded','duration_limit_us':2000000,'pair_tolerance_us':20000,
            'clock':'filename_time_unverified_utc','pairs':pairs,
            'algorithm_ready':False,'real_release_ready':False,'global_pose_available':False}
    accepted=[p for p in pairs if p['accepted']]
    if not accepted: raise ValueError('no_accepted_pairs')
    # Snapshot only accepted RGB/depth members, preserving names and actual hashes.
    members={}
    for pair in accepted:
        for key in ('depth','rgb'):
            name=pair[key]
            if name not in members:
                raw=(args.scene/name).read_bytes(); target=root/'raw'/name
                target.parent.mkdir(exist_ok=True); target.write_bytes(raw)
                members[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    report['members']=members
    selected=accepted[len(accepted)//2]
    depth=read_pnm((root/'raw'/selected['depth']).read_bytes(),True)
    rgb=read_pnm((root/'raw'/selected['rgb']).read_bytes())
    points,colors,pixels,color_valid,stats=make_cloud(depth,rgb)
    if not len(points): raise ValueError('empty_cloud')
    cloud=ply_bytes(points,colors,color_valid); (root/'frame.ply').write_bytes(cloud)
    # Preserve full-resolution valid-depth mask separately from sampled point export.
    code=depth.astype(float)
    with np.errstate(divide='ignore',invalid='ignore'): metric=351.3/(1092.5-code)
    mask=(code>=600)&(code<2047)&np.isfinite(metric)&(metric>0)&(metric<=10)
    (root/'depth-valid-mask.u8').write_bytes(mask.astype('u1').tobytes())
    (root/'rgb.png').write_bytes(png(rgb))
    normalized=np.clip(np.where(mask,metric,0)/10,0,1)
    image=np.stack([normalized*255,(1-normalized)*150,normalized*50],axis=-1).astype('u1')
    image[~mask]=0
    (root/'depth.png').write_bytes(png(image))
    # Orthographic depth-camera projection, preserving uncolored points in gray.
    preview=np.full((600,800,3),18,dtype='u1')
    x=(points[:,0]/points[:,2]*550+400).astype(int)
    y=(points[:,1]/points[:,2]*550+300).astype(int)
    inside=(x>=0)&(x<800)&(y>=0)&(y<600)
    for i in np.argsort(-points[:,2]):
        if inside[i]: preview[y[i],x[i]]=colors[i]
    (root/'cloud-preview.png').write_bytes(png(preview))
    np.savez(root/'point-associations.npz',depth_pixels=pixels,color_valid=color_valid)
    toolbox=Path('experiments/evidence/2026-10-28/nyu-offices-review-001/toolbox-source.zip')
    with zipfile.ZipFile(toolbox) as archive:
        (root/'camera_params.m').write_bytes(archive.read('camera_params.m'))
    report.update(selected_pair=selected,cloud={**stats,'sha256':hashlib.sha256(cloud).hexdigest(),
                  'bounds_m':[points.min(axis=0).tolist(),points.max(axis=0).tolist()],
                  'frame':'depth_optical','axes':['right','down','forward'],'unit':'m','stride':4},
                  calibration={'source':'NYU official toolbox camera_params.m',
                    'toolbox_sha256':hashlib.sha256(toolbox.read_bytes()).hexdigest(),
                    'color_method':'official R/T projection convention + inverse depth distortion + forward RGB distortion; nearest pixel',
                    'registration_quality_verified':False},
                  limitations=['single_frame_only','no_odometry_or_fusion','no_dynamic_scene_compensation',
                               'no_occlusion_consistency_for_color','no_independent_geometry_reference',
                               'unknown_is_not_free','no_depth_inpainting'])
    report['implementation_sha256']={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                  ('packages/data/nyu_rgbd.py','experiments/scripts/build_nyu_short_scene.py')}
    (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>NYU RGB-D 单帧核对</title>'
       '<style>body{background:#111827;color:#eee;font:14px sans-serif;margin:32px}img{width:32%;vertical-align:top}a{color:#60a5fa}</style>'
       '<h2>NYU办公室 · 单帧解码核对</h2><p>RGB / 深度（黑色为无有效深度） / 稀疏彩色点云投影</p>'
       '<img src="rgb.png"><img src="depth.png"><img src="cloud-preview.png">'
       '<p>坐标：深度相机局部系，单位米。单帧样例，无全局位姿、多帧融合或质量验收。</p>'
       '<a href="frame.ply">PLY 点云</a> · <a href="report.json">完整核对记录</a>',encoding='utf-8')
    print(json.dumps({'depth_frames':len(pairs),'accepted_pairs':len(accepted),'members':len(members),'cloud':report['cloud']}))


if __name__=='__main__': main()
