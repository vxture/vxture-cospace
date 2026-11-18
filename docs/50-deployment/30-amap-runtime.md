# AMap production integration

CoSpace uses the official AMap JavaScript API 2.0, with `normal` and `darkblue`
base-map styles. The experimental Tianditu layer is not part of this entry.

Create a **Web 端（JS API）** key and its security JS code. Store these only in
the production Environment secrets `COSPACE_AMAP_WEB_KEY` and
`COSPACE_AMAP_SECURITY_JS_CODE`. Do not add credentials to Vite variables,
source files, screenshots, logs or release archives.

After the required checks and production reviewer gate, deployment sends the
pair over SSH stdin to worker02. The remote helper atomically writes a mode-600
`/srv/md0/cospace/etc/amap.env`, outside the checkout. Compose reads that optional
runtime file. Blank release inputs preserve the existing configuration.

Authenticated, subscription-authorized clients read `/api/map/config`; only
the public JS key and same-origin service host are returned. The security code
stays server-side. `/_AMapService` proxies fixed official style,
coordinate-conversion and place-search endpoints, with bounded responses and no redirects.
Place search accepts only a keyword, uses the configured AMap integration,
and requests up to eight results. Verify the production key can call place
search from worker02 before accepting this feature.
Anonymous requests remain unauthorized.

Scene names and descriptions require `space.manage`. Location edits require
`space.location.edit`, granted to scene engineers and managers (and bound
workspace owners). Both sections use the same revision check and audit history. Store the original CRS
explicitly. GCJ02 anchors display directly; WGS84 anchors use the official
conversion API for a display copy. Missing coordinates remain unlocated.
No fixture coordinates or inferred geocoding are substituted into production.

Console restriction fields may vary. Check the selected JS API key's actual
controls. An IP whitelist needs the actual requesting server's public egress
address for proxied calls; a CDN ingress address is not equivalent. Browser SDK
calls must also work under that key's restrictions. Validate both from the
production browser before declaring acceptance; never solve a rejection by
silently switching to a different provider or disabling authentication.

Official references:
- https://lbs.amap.com/api/javascript-api-v2/prerequisites
- https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode

## 高程自动获取的选型

高德点选和地点搜索只返回二维坐标。当前表单的高度仍以测量资料为准。
地图选点只登记场景在地图上的位置，不校准模型、楼层或设备作业点。

- **室内、楼层和测量级定位**：采用现场控制点、已有测量记录或有明确地理基准的 IFC 勘测点。不能从二维地图推断楼层高度。
- **户外概览**：可评估 Copernicus DEM GLO-30（约 30 米网格，EGM2008 高程，属地表模型，可能包含建筑和植被）。接入前核实覆盖、许可及代表性偏差。只提供用户主动查询的参考值，标注数据集、版本、分辨率、基准和适用范围。
- **坐标与高程基准**：DEM 用 WGS84 水平坐标采样。对只有 GCJ02 的点，先取得可靠的 WGS84 坐标。海拔不能直接当作 WGS84 椭球高；绝对三维定位需要独立核对垂直基准及转换。缺数据时留空，不填 0，不覆盖实测值。

当前地址与位置保存合同不含独立高程来源和精度字段。接入自动参考值前应补齐这些元数据；正式登记仍由用户确认。
