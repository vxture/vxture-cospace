export const outcomeGuidance:Record<string,{label:string;advice:string;action:'publishing'|'integration'|'evidence'}>={
 historical_result:{label:'返回历史结果',advice:'仅返回固定版本历史证据，不表示实时可用；保持明确的版本与坐标系绑定。',action:'evidence'},
 observation_time_unverified:{label:'观测时效未核验',advice:'缺少经验证的观测时间，实时消费已被拒绝。核对采集证据与时钟；历史模式须由使用方显式接受。',action:'evidence'},
 publication_distribution_paused:{label:'版本已暂停',advice:'核对暂停原因；仅在完成核查后，通过发布管理恢复分发。',action:'publishing'},
 publication_retired:{label:'版本已退役',advice:'在发布管理核对替代版本，由调用方显式迁移；不自动切换版本。',action:'publishing'},
 consumer_version_mismatch:{label:'版本摘要不匹配',advice:'重新核对该固定发布的模型清单摘要，不混用其他版本的接入参数。',action:'integration'},
 consumer_frame_mismatch:{label:'坐标系不匹配',advice:'使用当前固定版本的 frame_id 与米制坐标，核对使用方坐标转换。',action:'integration'},
 consumer_space_denied:{label:'空间授权拒绝',advice:'由管理员核对平台租户、工作区与空间授权；不要复用其他空间凭据。',action:'integration'},
 consumer_publication_not_found:{label:'版本不存在',advice:'核对固定发布 ID 和所属空间；确认可用版本后由调用方显式选择。',action:'publishing'},
 consumer_request_or_publication_invalid:{label:'请求或成果无效',advice:'先核对请求字段和数值约束；若请求正确，再检查发布成果完整性。',action:'integration'},
 subscription_required:{label:'平台订阅授权拒绝',advice:'联系平台管理员核对订阅权益；本产品不签发商业授权。',action:'integration'},
 consumer_dependency_unavailable:{label:'依赖暂不可用',advice:'核对平台身份、授权配置、存储和服务日志；恢复后由调用方按接入约定重试。',action:'integration'},
};
export function diagnosticGuidance(outcome:string){return outcomeGuidance[outcome]||{label:'未分类结果',advice:'核对当前接口协议及服务日志，保留固定版本，不根据未知结果自动继续消费。',action:'integration' as const};}
export const lifecycleLabels:Record<string,string>={active:'允许分发',paused:'已暂停',retired:'已退役',unavailable:'状态待核对'};
