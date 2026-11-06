"""Bounded NYU raw RGB-D decoding and inspection cloud; no global reconstruction."""
from decimal import Decimal
import re
import numpy as np

DEPTH_K=np.array([582.6244816773796,582.6910327098864,313.0447587080473,238.44389626620386])
RGB_K=np.array([518.8579011745019,519.4696111212749,325.58244941119034,253.73616633400465])
DEPTH_D=np.array([-.09989723655308448,.39065324602765344,.0019290592870229277,-.0019422022475975055,-.5103172505340058])
RGB_D=np.array([.20796615318809061,-.58613825163911781,.00072231363135888329,.0010479627195765181,.49856986684705107])
# Literal MATLAB reshape/inverse convention from the official toolbox; only used for color projection.
_R=-np.array([.99997798940829263,.0050518419386157446,.0043011152014118693,
             -.0050359919480810989,.99998051861143999,-.0036879781309514218,
             -.0043196624923060242,.0036662365748484798,.99998394948385538]).reshape((3,3),order='F')
COLOR_R=np.linalg.inv(_R.T)
COLOR_T=np.array([.025031875059141302,-.00029342312935846411,.00066238747008330102])


def timestamp_us(name):
    match=re.fullmatch(r'[dra]-(\d+\.\d{1,6})-\d+\.(?:pgm|ppm|dump)',name)
    if not match: raise ValueError('filename_timestamp')
    return int(Decimal(match[1])*1000000)


def read_pnm(raw,depth=False):
    if len(raw)>2000000: raise ValueError('pnm_budget')
    match=re.match(rb'(P[56])\s+(\d+)\s+(\d+)\s+(\d+)[ \t\r\n]',raw)
    if not match: raise ValueError('unsupported_pnm_header')
    magic,w,h,maximum=match.groups(); w,h=int(w),int(h)
    profile=(b'P5',b'65535') if depth else (b'P6',b'255')
    if (w,h)!=(640,480) or (magic,maximum)!=profile:
        raise ValueError('unsupported_pnm_profile')
    payload=raw[match.end():]
    expected=w*h*(2 if depth else 3)
    if len(payload)!=expected: raise ValueError('pnm_payload_length')
    # NYU stores little endian words despite PGM convention; equivalent to MATLAB imread + swapbytes.
    return np.frombuffer(payload,dtype='<u2' if depth else 'u1').reshape((h,w) if depth else (h,w,3)).copy()


def distort(x,y,coefficients):
    k1,k2,p1,p2,k3=coefficients
    r2=x*x+y*y; radial=1+k1*r2+k2*r2*r2+k3*r2*r2*r2
    return x*radial+2*p1*x*y+p2*(r2+2*x*x), y*radial+p1*(r2+2*y*y)+2*p2*x*y


def make_cloud(depth,rgb,stride=4):
    if depth.shape!=(480,640) or rgb.shape!=(480,640,3): raise ValueError('image_shape')
    if type(stride) is not int or stride<1 or stride>32: raise ValueError('stride')
    v,u=np.mgrid[0:480:stride,0:640:stride]
    code=depth[::stride,::stride].astype(float)
    with np.errstate(divide='ignore',invalid='ignore'):
        z=351.3/(1092.5-code)
    # Keep only finite supported range. Never clamp far/invalid returns onto a fake surface.
    valid=(code>=600)&(code<2047)&np.isfinite(z)&(z>0)&(z<=10)
    xd=(u+1-DEPTH_K[2])/DEPTH_K[0]; yd=(v+1-DEPTH_K[3])/DEPTH_K[1]
    x,y=xd.copy(),yd.copy()
    for _ in range(15):
        dx,dy=distort(x,y,DEPTH_D); x+=xd-dx; y+=yd-dy
    rx,ry=distort(x,y,DEPTH_D)
    valid &= np.isfinite(x)&np.isfinite(y)&(np.abs(rx-xd)<1e-7)&(np.abs(ry-yd)<1e-7)
    points=np.stack([x*z,y*z,z],axis=-1)[valid]
    # Retain source pixel association, including missing color; no global pose is fabricated.
    pixels=np.stack([u,v],axis=-1)[valid]
    projected=points@COLOR_R.T+COLOR_T
    cx,cy=distort(projected[:,0]/projected[:,2],projected[:,1]/projected[:,2],RGB_D)
    col=np.rint(cx*RGB_K[0]+RGB_K[2]-1).astype(int)
    row=np.rint(cy*RGB_K[1]+RGB_K[3]-1).astype(int)
    color_valid=(col>=0)&(col<640)&(row>=0)&(row<480)
    colors=np.full((len(points),3),150,dtype=np.uint8)
    colors[color_valid]=rgb[row[color_valid],col[color_valid]]
    return points,colors,pixels,color_valid,{'sampled_pixels':int(code.size),'valid_points':len(points),
        'invalid_or_unresolved_pixels':int(code.size-len(points)),'colored_points':int(color_valid.sum())}


def ply_bytes(points,colors,color_valid):
    header=('ply\nformat ascii 1.0\ncomment frame depth_optical x_right y_down z_forward unit_m\n'
            f'element vertex {len(points)}\nproperty float x\nproperty float y\nproperty float z\n'
            'property uchar red\nproperty uchar green\nproperty uchar blue\nproperty uchar color_valid\nend_header\n')
    rows=['%.6f %.6f %.6f %d %d %d %d'%(*point,*color,int(ok)) for point,color,ok in zip(points,colors,color_valid)]
    return (header+'\n'.join(rows)+'\n').encode()
