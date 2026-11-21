"""Interpret explicit axis directions without inferring them from geometry or XYZ."""
import re
import unicodedata


ALIASES = {
    'right': ('right', 'r', '右', '向右'),
    'left': ('left', 'l', '左', '向左'),
    'forward': ('forward', 'front', 'f', '前', '向前'),
    'backward': ('backward', 'back', 'rear', 'b', '后', '向后'),
    'up': ('up', 'u', '上', '向上'),
    'down': ('down', 'd', '下', '向下'),
    'east': ('east', 'e', '东', '向东'),
    'west': ('west', 'w', '西', '向西'),
    'north': ('north', 'n', '北', '向北'),
    'south': ('south', 's', '南', '向南'),
}
DIRECTIONS = {alias: name for name, aliases in ALIASES.items() for alias in aliases}
BASIS = {'right': (1, 0, 0), 'left': (-1, 0, 0), 'forward': (0, 1, 0),
         'backward': (0, -1, 0), 'up': (0, 0, 1), 'down': (0, 0, -1),
         'east': (1, 0, 0), 'west': (-1, 0, 0), 'north': (0, 1, 0), 'south': (0, -1, 0)}


def valid_axis_label(value):
    return (isinstance(value, str) and len(value) <= 40
            and re.fullmatch(r'[^\W\d_][\w ()（）+\-]{0,39}', value, re.UNICODE) is not None)


def direction(value, index):
    if not valid_axis_label(value):
        return None
    label = unicodedata.normalize('NFKC', value).strip().lower()
    # Optional axis prefixes are accepted only in their corresponding column.
    match = re.fullmatch(r'([xyz])(?:轴|[_\- ]|\()(.+?)\)?', label)
    if match:
        if match[1] != 'xyz'[index]:
            return None
        label = match[2]
    return DIRECTIONS.get(label.strip())


def registration_readiness(axes, unit='m'):
    raw = list(axes) if isinstance(axes, (list, tuple)) else []
    normalized = [direction(value, index) for index, value in enumerate(raw)] if len(raw) == 3 else []
    status = 'needs_declaration'
    if unit != 'm':
        status = 'unsupported_unit'
    elif len(normalized) == 3 and all(normalized):
        relative = set(normalized) & {'right', 'left', 'forward', 'backward'}
        geographic = set(normalized) & {'east', 'west', 'north', 'south'}
        a, b, c = [BASIS[value] for value in normalized]
        determinant = (a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0])
                       + a[2]*(b[0]*c[1]-b[1]*c[0]))
        status = ('invalid_axes' if relative and geographic else
                  'ready' if determinant == 1 else 'left_handed' if determinant == -1 else 'invalid_axes')
    messages = {
        'ready': ('轴向可用于配准', '已识别明确的右手轴向；仍需控制点、目标基准及独立核验。'),
        'needs_declaration': ('配准前需补齐轴向', '按来源资料明确三轴方向。X/Y/Z 或 sensor_x 等名称本身不能确定方向。'),
        'left_handed': ('当前为左手轴向', '核对来源坐标约定；本配准路线只接受右手坐标，不能仅改标签掩盖实际坐标转换。'),
        'invalid_axes': ('轴向不能构成明确的三维坐标系', '三轴存在重复、共线或混用相对方向与地理方向，请按同一来源坐标约定修订。'),
        'unsupported_unit': ('配准需要米制模型', '先按实际单位转换数据后重新导入；修改声明不会换算点坐标。'),
    }
    title, action = messages[status]
    return {'status': status, 'title': title, 'action': action, 'unit': unit,
            'axes': raw, 'resolved_axes': normalized, 'basis': 'explicit_axis_aliases/1',
            'coordinate_transform_applied': False}
