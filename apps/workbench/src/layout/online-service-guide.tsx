import React from 'react';
import {StatusBadge} from '@vxture/design-system';
import type {SpatialService} from './spatial-service-contract';

export function OnlineServiceGuide({item}:{item:SpatialService}){
 const path=`/s2s/spaces/${item.scene.id}/publications/${item.release.id}/query`;
 return <section className="flex flex-col gap-md" aria-label="具身智能体接入说明">
  <h3 className="text-body font-medium">具身智能体接入</h3><StatusBadge tone="warning">当前成果观测时效未核验</StatusBadge>
  <p className="text-body-small text-muted-foreground">由平台管理员配置服务身份与当前空间授权，使用平台签发的短期服务票据调用以下固定版本接口。网页查询使用个人会话，两者独立。</p>
  <pre className="spatial-service-example">{`POST ${path}\nAuthorization: Bearer <平台短期服务票据>\nContent-Type: application/json\n\n${JSON.stringify({model_manifest_sha256:item.release.model_manifest_sha256||'替换为当前固定版本的模型清单摘要',frame_id:'使用当前版本空间描述中的 frame_id',point_m:[0,0,0],mode:'operational',max_age_s:60,accept_unverified_time:false},null,2)}`}</pre>
  <p className="text-label-small text-muted-foreground">当前 operational 请求返回 HTTP 200、status: refused、refusal: observation_time_unverified，不代表可用于实时决策。仅在明确接受未核验时间的历史证据时，使用 historical 并显式设置 accept_unverified_time: true。</p>
  <p className="text-label-small text-muted-foreground">409：版本摘要、坐标系不匹配，或发布已暂停/退役；401/403：身份或授权被拒；503：依赖不可用。拒绝后应停止消费并核对原因，不自动切换版本。服务端在返回前重新核对授权与发布状态。</p>
 </section>;
}
