import base64
import json
from pathlib import Path
import struct
import zlib

import numpy as np
import pytest
from packages.data.rgbd_input_preview import directory, frame, depth_display, png, encoded, MAX_FRAME, MAX_INDEX
from packages.data.input_preview import PreviewUnavailable
from packages.construction.preview_model import digest
from test_build_process import temporal
from test_preview_batches import files
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_preview_inputs import source


def read_png(data):
    raw = base64.b64decode(data.split(',')[1]); assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    w,h,depth,kind = struct.unpack('>IIBB', raw[16:26]); assert depth == 8
    offset=8; chunks=[]
    while offset < len(raw):
        n=struct.unpack('>I',raw[offset:offset+4])[0];tag=raw[offset+4:offset+8];part=raw[offset+8:offset+8+n]
        assert zlib.crc32(tag+part)&0xffffffff==struct.unpack('>I',raw[offset+8+n:offset+12+n])[0]
        if tag==b'IDAT':chunks.append(part)
        offset+=n+12
    pixels=zlib.decompress(b''.join(chunks));channels=4 if kind==6 else 3
    rows=np.frombuffer(pixels,dtype=np.uint8).reshape(h,1+w*channels);assert not rows[:,0].any()
    return rows[:,1:].reshape(h,w,channels)


def test_read_only_directory_frame_bound_and_schema(tmp_path,monkeypatch):
    jobs,space,record,snapshot,tracking=temporal(tmp_path)
    monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('no worker poll'))
    before=files(tmp_path);value=directory(jobs.inputs,record['id'],space);image=frame(jobs.inputs,record['id'],space,0)
    assert value['input_frames']==4 and value['pose_frames']==3 and value['frames'][3]['pose'] is None
    assert image['frame']==value['frames'][0] and image['payload_checked']=='selected_pair_only'
    assert value['frames'][2]['relative_time_us']==60000 and not value['payload_checked']
    assert files(tmp_path)==before and image==frame(jobs.inputs,record['id'],space,0)
    assert read_png(image['rgb_png']).shape==(240,320,3)
    assert image['valid_depth_pixels']==640*480 and read_png(image['depth_png'])[:,:,3].min()==255
    assert 'snapshot' not in value and 'tracking' not in value
    from jsonschema import Draft202012Validator
    schema=json.loads(Path('contracts/schemas/rgbd-input-preview-v0.1.schema.json').read_bytes())
    Draft202012Validator(schema).validate(value);Draft202012Validator(schema).validate(image)
    with pytest.raises(PermissionError):directory(jobs.inputs,record['id'],'space-wrong')


@pytest.mark.parametrize('code,valid',[ (0,False),(599,False),(600,True),(1000,True),(1057,True),(1058,False),(1093,False),(2047,False),(65535,False)])
def test_nyu_depth_codes_metres_mask_and_fixed_palette(code,valid):
    rgba,count=depth_display(np.full((480,640),code,dtype=np.uint16))
    assert count==(480*640 if valid else 0) and (rgba[0,0,3]==255)==valid
    if valid:
        t=(351.3/(1092.5-code))/10
        assert rgba[0,0,:3].tolist()==np.array([t*255,(1-abs(2*t-1))*255,(1-t)*255],dtype=np.uint8).tolist()
    else:assert not rgba.any()


def test_selected_pair_only_missing_member_and_independent_old_time(tmp_path):
    jobs,space,record,snapshot,tracking=temporal(tmp_path)
    v=json.loads((snapshot/'report.json').read_bytes());v['pairs'][3]['depth']='missing.pgm';v['members']['missing.pgm']=v['members']['d.pgm']
    for p in v['pairs']:p.pop('depth_time_us',None)
    (snapshot/'report.json').write_text(json.dumps(v));t=json.loads(tracking.read_bytes());t['source_report_sha256']=digest(snapshot/'report.json');tracking.write_text(json.dumps(t))
    # Update only this independent fixture's fixed registration to test a legacy manifest.
    p=jobs.inputs.root/(record['id']+'.json');r=json.loads(p.read_bytes());r.update(snapshot_sha256=digest(snapshot/'report.json'),tracking_sha256=digest(tracking));p.write_text(json.dumps(r))
    assert directory(jobs.inputs,record['id'],space)['frames'][0]['relative_time_us'] is None
    assert frame(jobs.inputs,record['id'],space,0)['frame']['index']==0
    with pytest.raises(PreviewUnavailable):frame(jobs.inputs,record['id'],space,3)


@pytest.mark.parametrize('index',[-1,True,4,500,1.1,'1'])
def test_invalid_frame_indices(tmp_path,index):
    jobs,space,record,_,_=temporal(tmp_path)
    with pytest.raises(PreviewUnavailable):frame(jobs.inputs,record['id'],space,index)


@pytest.mark.parametrize('member',['report.json','tracking','raw/d.pgm','raw/r.ppm'])
def test_mutation_not_cached(tmp_path,member):
    jobs,space,record,snapshot,tracking=temporal(tmp_path)
    frame(jobs.inputs,record['id'],space,0)
    (tracking if member=='tracking' else snapshot/member).write_bytes(b'changed')
    with pytest.raises(PreviewUnavailable):frame(jobs.inputs,record['id'],space,0)


@pytest.mark.parametrize('case',['pose','reflection','order','name','size','duplicate','count','nan'])
def test_invalid_bound_manifests(tmp_path,case):
    jobs,space,record,snapshot,tracking=temporal(tmp_path);v=json.loads((snapshot/'report.json').read_bytes());t=json.loads(tracking.read_bytes())
    if case=='pose':t['prefix_T_anchor_camera'][0][0][0]=2
    if case=='reflection':t['prefix_T_anchor_camera'][0][0][0]=-1
    if case=='nan':t['prefix_T_anchor_camera'][0][0][0]=float('nan')
    if case=='order':v['pairs'][1]['depth_time_us']=v['pairs'][0]['depth_time_us']
    if case=='name':v['pairs'][0]['depth']='../d.pgm'
    if case=='size':v['members']['d.pgm']['bytes']=2_000_001
    if case=='count':v['pairs']*=126
    raw=json.dumps(v)
    if case=='duplicate':raw=raw.replace('"pairs":','"pairs": [], "pairs":',1)
    (snapshot/'report.json').write_text(raw);t['source_report_sha256']=digest(snapshot/'report.json');tracking.write_text(json.dumps(t))
    p=jobs.inputs.root/(record['id']+'.json');r=json.loads(p.read_bytes());r.update(snapshot_sha256=digest(snapshot/'report.json'),tracking_sha256=digest(tracking));p.write_text(json.dumps(r))
    with pytest.raises(PreviewUnavailable):directory(jobs.inputs,record['id'],space)


def test_worst_case_png_and_response_budget():
    random=np.random.default_rng(12).integers(0,256,(240,320,4),dtype=np.uint8)
    rgb=png(random[:,:,:3]);depth=png(random)
    assert len(json.dumps(encoded({'rgb_png':rgb,'depth_png':depth},MAX_FRAME)))<MAX_FRAME
    assert np.array_equal(read_png(depth),random)
    with pytest.raises(ValueError):encoded({'large':'x'*MAX_INDEX},MAX_INDEX)


def test_missing_original_blocks_new_use_but_keeps_fixed_process(tmp_path):
    import time
    from packages.construction.build_process import read_process
    jobs,space,record,snapshot,_=temporal(tmp_path)
    job=jobs.start(record['id'],space)
    for _ in range(500):
        job=next(j for j in jobs.list() if j['id']==job['id'])
        if job['state'] not in ('queued','running'):break
        time.sleep(.03)
    assert job['state']=='succeeded'
    before=read_process(jobs,space,job['id']);(snapshot/'raw/d.pgm').unlink()
    with pytest.raises(PreviewUnavailable):frame(jobs.inputs,record['id'],space,0)
    assert read_process(jobs,space,job['id'])==before
    with pytest.raises((OSError,ValueError)):jobs.start(record['id'],space)


@pytest.mark.parametrize('user,allowed',[('usr_local_test',False),('usr_other',False),('usr_engineer',True),('usr_manager',True)])
def test_rgbd_http_authorization_and_errors(secured,user,allowed,monkeypatch):
    _,client,_,_,jobs,_,spaces,*_=secured;root=jobs.root.parent/'rgbd-new';root.mkdir();snapshot,tracking=source(root)
    r=jobs.inputs.register('RGB-D',snapshot,tracking,spaces[0]['id']);url='/api/inputs/'+r['id']+'/rgbd-preview';q={'space_id':spaces[0]['id']}
    assert client.get(url,params=q).status_code==401
    headers,_=sign_in(secured,user)
    monkeypatch.setattr(jobs,'poll',lambda:pytest.fail('read cannot poll'))
    for suffix in ('','/frame'):
        params=q|({'frame_index':'0'} if suffix else {})
        response=client.get(url+suffix,params=params);assert response.status_code==(200 if allowed else 403),response.text
        if allowed:
            assert response.headers['cache-control']=='no-store'
            assert client.get(url+suffix,params=params|{'path':'outside'}).status_code==422
            assert client.get(url+suffix,params=list(params.items())+[('space_id',q['space_id'])]).status_code==403
        assert client.get(url+suffix,params=params|{'space_id':spaces[1]['id']}).status_code==403
        assert client.post(url+suffix,json=params,headers=headers).status_code==403
    if allowed:
        for invalid in ('-1','01','1.1','500','1000'):
            assert client.get(url+'/frame',params=q|{'frame_index':invalid}).status_code in (409,422)
        (snapshot/'raw/d.pgm').unlink();assert client.get(url+'/frame',params=q|{'frame_index':'0'}).status_code==409
        assert client.get(url,params=q).status_code==200
