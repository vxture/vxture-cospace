export function publicationForTarget<T extends {id:string;candidate_id:string}>(ordered:readonly T[],target:{publication?:string;job?:string}):T|undefined{
 if(target.publication)return ordered.find(item=>item.id===target.publication);
 if(target.job)return ordered.find(item=>item.candidate_id===target.job);
 return ordered[0];
}
