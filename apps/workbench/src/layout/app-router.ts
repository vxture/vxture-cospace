import type {createBrowserRouter} from 'react-router-dom';

// One History router owns module navigation, record context and browser history.
type AppRouter=ReturnType<typeof createBrowserRouter>;
let router:AppRouter;
export function bindAppRouter(value:AppRouter){router=value;}
export function appNavigate(href:string,replace=false){void router.navigate(href.startsWith('/')?href:'/'+href,{replace});}
export const appLocation=()=>location.pathname+location.search;
export const subscribeAppLocation=(update:()=>void)=>router.subscribe(update);
export const appRoute=()=>location.pathname.slice(1)||'space';
