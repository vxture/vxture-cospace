"""NCLT ms25 CSV byte inspection; records declared units without inventing frames."""
import csv
import hashlib
import io
import math
import re

MAX_BYTES=64*1024*1024
MAX_ROWS=1000000
COLUMNS=[('utime','us'),('mag_x','Gauss'),('mag_y','Gauss'),('mag_z','Gauss'),
         ('accel_x','m/s^2'),('accel_y','m/s^2'),('accel_z','m/s^2'),
         ('rot_r','rad/s'),('rot_p','rad/s'),('rot_h','rad/s')]


def inspect_ms25(raw, expected_sha256=None):
    if type(raw) is not bytes: raise ValueError('bytes_required')
    report={'schema_version':'cospace.nclt-ms25-preflight/0.1',
            'input':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                     'expected_digest_verified':False},
            'columns':[{'name':name,'declared_unit':unit} for name,unit in COLUMNS],
            'rows_seen':0,'valid_rows':0,'invalid_rows':0,
            'time':{'start_us':None,'end_us':None,'backward_steps':0,'duplicate_steps':0,
                    'min_positive_delta_us':None,'max_positive_delta_us':None},
            'ranges':{},'errors':[],'structural_precheck_passed':False,
            'algorithm_ready':False,'real_release_ready':False,
            'unverified':['lidar_not_inspected','sensor_clock_mapping','sensor_axes_and_extrinsics',
                          'imu_attitude','independent_quality']}
    errors=[]
    def fail(code,row=None):
        if len(errors)<32: errors.append({'code':code,'row':row})
    if len(raw)>MAX_BYTES: fail('file_budget')
    elif expected_sha256 is not None and report['input']['sha256']!=expected_sha256: fail('input_digest_mismatch')
    else:
        report['input']['expected_digest_verified']=expected_sha256 is not None
        previous=None
        try:
            reader=csv.reader(io.StringIO(raw.decode('ascii'),newline=''),strict=True)
            for number,row in enumerate(reader,1):
                report['rows_seen']+=1
                if number>MAX_ROWS:
                    fail('row_budget',number); break
                try:
                    if len(row)!=10: raise ValueError('column_count')
                    if not re.fullmatch(r'[0-9]{1,19}',row[0]) or not 0<int(row[0])<=9223372036854775807:
                        raise ValueError('invalid_timestamp')
                    at=int(row[0]); values=[float(value) for value in row[1:]]
                    if not all(map(math.isfinite,values)): raise ValueError('non_finite_value')
                except ValueError as error:
                    report['invalid_rows']+=1
                    fail(str(error) if str(error) in ('column_count','invalid_timestamp','non_finite_value') else 'invalid_numeric',number)
                    continue
                report['valid_rows']+=1
                time=report['time']
                if previous is not None:
                    delta=at-previous
                    time['backward_steps']+=int(delta<0)
                    time['duplicate_steps']+=int(delta==0)
                    if delta>0:
                        time['min_positive_delta_us']=min(delta,time['min_positive_delta_us'] or delta)
                        time['max_positive_delta_us']=max(delta,time['max_positive_delta_us'] or delta)
                previous=at
                time['start_us']=min(at,time['start_us'] if time['start_us'] is not None else at)
                time['end_us']=max(at,time['end_us'] if time['end_us'] is not None else at)
                for (name,_),value in zip(COLUMNS[1:],values):
                    bounds=report['ranges'].setdefault(name,[value,value])
                    bounds[0]=min(bounds[0],value); bounds[1]=max(bounds[1],value)
        except (UnicodeDecodeError,csv.Error): fail('csv_decode_failed')
        if report['valid_rows']<2: fail('insufficient_rows')
        if report['time']['backward_steps'] or report['time']['duplicate_steps']: fail('non_increasing_time')
    report['errors']=errors
    report['structural_precheck_passed']=not errors
    return report
