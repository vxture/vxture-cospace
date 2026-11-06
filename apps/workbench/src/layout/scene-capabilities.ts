import {createContext,useContext} from 'react';
export const SceneCapabilities=createContext<string[]>([]);
export const useSceneCapabilities=()=>useContext(SceneCapabilities);
