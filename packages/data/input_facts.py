"""Bounded manifest facts. Never infers UTC, alignment, or payload integrity."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from packages.data.input_descriptions import InputDescriptions


class FactsUnavailable(RuntimeError):
    pass


def facts(catalog, identity, space_id):
    record = InputDescriptions(catalog).original(identity, space_id)
    result = {'profile': 'cospace.input-facts/0.1', 'space_id': space_id, 'input_id': identity,
              'read_at': datetime.now(timezone.utc).isoformat(), 'fields': {}, 'roles': [],
              'evidence': [], 'payload_checked': False, 'cache_policy': 'bounded_manifests_rechecked_per_request',
              'quality': 'unverified', 'robot_ready': False}

    def load(path, expected, member, limit=2_000_000):
        try:
            with Path(path).open('rb') as stream:
                raw = stream.read(limit+1)
        except OSError as exc:
            raise FactsUnavailable('input_evidence_unreadable') from exc
        if len(raw) > limit:
            raise FactsUnavailable('input_evidence_budget')
        sha = hashlib.sha256(raw).hexdigest()
        if sha != expected:
            raise FactsUnavailable('input_evidence_changed')
        result['evidence'].append({'member': member, 'sha256': sha, 'status': 'manifest_digest_matches'})
        return json.loads(raw)

    def field(key, value, member, pointer, kind='source_declaration'):
        result['fields'][key] = {'value': value, 'status': 'known' if value is not None else 'unknown',
                                 'evidence_ref': {'member': member, 'field': pointer}, 'basis': kind}

    try:
        if record['format'] == 'ply_pointcloud':
            doc = load(Path(record['snapshot'])/'pointcloud.json', record['snapshot_sha256'], 'pointcloud.json', 64_000)
            if doc['profile'] != 'cospace.pointcloud-input/0.1':raise ValueError('format')
            for key in ('unit','frame_id','axes','scope'):
                revision=record.get('coordinate_revision')
                field(key, revision['coordinates'][key] if revision else doc['coordinates'][key],
                      'coordinate_revision' if revision else 'pointcloud.json', 'coordinates.'+key)
            field('scene_alignment', None, 'pointcloud.json', 'coordinates.scene_alignment')
            field('point_count', doc['cloud']['points'], 'pointcloud.json', 'cloud.points')
            if doc.get('source_receipt_path')=='source.json':
                from packages.data.preview_pointcloud import source_receipt
                receipt=source_receipt(Path(record['snapshot']),doc)
                load(Path(record['snapshot'])/'source.json',doc['provenance']['source_manifest_sha256'],'source.json',64_000)
                field('source_basis',receipt['basis'],'source.json','basis')
                field('original_name',receipt['original_name'],'source.json','original_name')
                field('source_description',receipt['description'],'source.json','description')
            if doc.get('composition_path')=='composition.json':
                from packages.data.pointcloud_composition import read_composition
                load(Path(record['snapshot'])/'composition.json',doc['provenance']['source_manifest_sha256'],'composition.json',64_000)
                receipt=read_composition(Path(record['snapshot']),doc)
                field('composition_sources',[s['name'] for s in receipt['sources']],'composition.json','sources[].name')
                for key in ('matched_points','retained_points','bounds_local','voxel_size'):
                    field(key,receipt[key],'composition.json',key)
                field('composition_unit_basis','仅流程验证假定米制，未核验' if receipt['unit_basis']=='assumed_metre_for_flow_validation' else '提供者声明已核验米制',
                      'composition.json','unit_basis')
                field('source_description',receipt['description'],'composition.json','description')
            result['roles'] = [{'role':'已有点云成果','use':'保留声明坐标，规范化为固定模型后派生双视图'}]
            result['limitations'] = ['来源与坐标由提供者声明，未独立复核', '未执行配准、SLAM或空闲推断']
        elif record['format'] in ('ros1_lidar_single_frame','ros1_lidar_multiframe_icp'):
            doc = load(Path(record['snapshot'])/'sample.json', record['snapshot_sha256'], 'sample.json', 256_000)
            if doc['profile'] != 'cospace.external-lidar-specimen/0.1':
                raise ValueError('format')
            first = doc['first_frame']
            field('unit', first.get('unit'), 'sample.json', 'first_frame.unit')
            field('frame_id', first.get('frame_id'), 'sample.json', 'first_frame.frame_id')
            field('recorded_window_ns', {k:str(v) for k,v in doc['recorded_window'].items()}, 'sample.json', 'recorded_window')
            header=first['from_message'].get('header_ns')
            field('sensor_header_ns', str(header) if header is not None else None, 'sample.json', 'first_frame.from_message.header_ns')
            field('scene_alignment', None, 'sample.json', 'first_frame.frame_id')
            mapping=record['format']=='ros1_lidar_multiframe_icp'
            result['roles'] = [
                {'role': '激光观测', 'use': '多帧参与纯激光配准，形成首帧局部模型和估计轨迹' if mapping else '仅首帧用于局部候选，其余帧用于输入核对'},
                {'role': 'IMU', 'use': '仅核对消息，不参与融合'}]
            result['limitations'] = (['首帧局部坐标；无现场对齐、回环或运动畸变补偿','IMU和参考位姿未用于建图','消息时间未验证UTC同步'] if mapping else ['传感器局部坐标，未配准、未执行SLAM', '首帧强度显示不代表相机彩色'])
        elif record['format'] == 'nyu_rgbd_with_existing_poses':
            doc = load(Path(record['snapshot'])/'report.json', record['snapshot_sha256'], 'report.json')
            tracking = load(record['tracking'], record['tracking_sha256'], 'tracking.json')
            if (doc['schema_version'] != 'cospace.nyu-short-scene/0.1'
                    or tracking['source_report_sha256'] != record['snapshot_sha256']):
                raise ValueError('format_or_tracking_binding')
            from packages.data.nyu_rgbd import timestamp_us
            pairs = [p for p in doc['pairs'] if p['accepted']]
            try:times = [timestamp_us(p['depth']) for p in pairs]
            except ValueError:times = []
            field('unit', 'm', 'nyu_rgbd_adapter', 'depth_to_metres', 'adapter_interpretation')
            field('frame_id', 'first_depth_camera_anchor', 'tracking.json', 'prefix_T_anchor_camera', 'adapter_interpretation')
            field('image_window_us', {'start_us': min(times), 'end_inclusive_us': max(times)} if times else None, 'report.json', 'pairs[].depth', 'filename_interpretation')
            field('source_clock', doc.get('clock'), 'report.json', 'clock')
            field('scene_alignment', None, 'tracking.json', 'prefix_T_anchor_camera')
            result['roles'] = [
                {'role': '彩色与深度观测', 'use': '用于当前RGB-D构建路线'},
                {'role': '已有轨迹', 'use': '按固定prefix_T_anchor_camera使用，不生成新轨迹'},
                {'role': '标定', 'use': '沿用适配器明确的NYU相机参数，不代表现场复核'}]
            result['limitations'] = ['局部基准未与现场坐标对齐', '已有轨迹与适配参数不代表精度验收']
        else:
            raise FactsUnavailable('input_facts_format_not_supported')
        field('utc_sync', None, 'input_adapter', 'no_verified_clock_mapping')
        field('epsg', None, 'input_adapter', 'local_coordinates')
        if 'axes' not in result['fields']:field('axes', None, 'input_adapter', 'no_verified_scene_axes')
        result['limitations'].append('仅核对清单摘要；未重新检查数据文件，构建仍执行实时预检')
        return result
    except FactsUnavailable:
        raise
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        raise FactsUnavailable('input_evidence_invalid') from exc
