// JSON.parse supplies syntax checking; this pass rejects ambiguous keys and deep nesting.
export function checkedJsonFile(text:string,maximumBytes:number):unknown{
 if(new TextEncoder().encode(text).length>maximumBytes)throw new Error('文件过大。');
 const value:unknown=JSON.parse(text);
 const stack:(Set<string>|null)[]=[];
 // Skip entire strings, so braces or colons inside values cannot become tokens.
 for(const [token,keyToken] of text.matchAll(/("(?:[^"\\]|\\.)*")[\t\n\r ]*:|"(?:[^"\\]|\\.)*"|[{}[\]]/g)){
  if(keyToken){
   const keys=stack.at(-1)!;
   const key=JSON.parse(keyToken) as string;
   if(keys.has(key))throw new Error('JSON 存在重复字段。');
   keys.add(key);
  }else if(token==='{'||token==='['){
   stack.push(token==='{'?new Set():null);
   if(stack.length>64)throw new Error('JSON 层级过深。');
  }else if(token==='}'||token===']')stack.pop();
 }
 return value;
}
