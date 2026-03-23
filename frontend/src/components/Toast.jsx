import { useState, useEffect } from 'react';
import { theme, css } from '../theme';
import { Icon, I } from './UI';

export default function ToastItem({message,type="success",onClose}){
  const[closing,setClosing]=useState(false);
  const dismiss=()=>{setClosing(true);setTimeout(onClose,250);};
  useEffect(()=>{const t=setTimeout(dismiss,3000);return()=>clearTimeout(t);},[]);
  const types={
    success:{color:theme.accent,bg:theme.accentSoft,icon:I.check,label:"Erfolg"},
    error:{color:theme.danger,bg:theme.dangerSoft,icon:I.x,label:"Fehler"},
    info:{color:theme.blue,bg:theme.blueSoft,icon:I.help,label:"Info"}
  };
  const c=types[type]||types.success;
  return(<div style={{animation:closing?"toastOut 0.25s ease forwards":"toastIn 0.3s ease",display:"flex",alignItems:"stretch",background:theme.card,border:`1px solid ${theme.border}`,borderRadius:10,boxShadow:"0 4px 20px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.03)",maxWidth:370,minWidth:260,fontFamily:"'DM Sans', system-ui, sans-serif",overflow:"hidden"}}>
    <div style={{width:4,background:c.color,flexShrink:0,borderRadius:"10px 0 0 10px"}}/>
    <div style={{display:"flex",alignItems:"center",gap:10,padding:"12px 14px",flex:1}}>
      <div style={{width:28,height:28,borderRadius:8,background:c.bg,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,border:`1px solid ${c.color}22`}}><Icon d={c.icon} size={14} color={c.color}/></div>
      <span style={{fontSize:13,color:theme.text,fontWeight:500,flex:1,lineHeight:1.4}}>{message}</span>
      <div style={{cursor:"pointer",padding:4,borderRadius:6,transition:"background 0.15s",flexShrink:0}} onClick={dismiss} onMouseEnter={e=>e.currentTarget.style.background=theme.surfaceAlt} onMouseLeave={e=>e.currentTarget.style.background="transparent"}><Icon d={I.x} size={12} color={theme.textDim}/></div>
    </div>
  </div>);
}
