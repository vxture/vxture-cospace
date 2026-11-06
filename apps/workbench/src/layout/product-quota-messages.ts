const messages:Record<string,string>={
 QUOTA_EXCEEDED:'平台返回额度不足，请在平台查看当前工作区的权益。',
 NOT_ENTITLED:'平台尚未授权此操作，请在平台查看当前工作区的权益。',
};
export function productQuotaMessage(detail:unknown):string|undefined{
 return typeof detail==='string'&&Object.hasOwn(messages,detail)?messages[detail]:undefined;
}
