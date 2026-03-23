import { useState } from 'react';
import { theme } from '../theme';
import { Icon, I, ATLogo } from './UI';

export default function Sidebar({active,onNav,onLogout,collapsed}){
  const items=[{id:"dashboard",icon:I.dashboard,label:"Dashboard"},{id:"invoices",icon:I.invoice,label:"Rechnungen"},{id:"upload",icon:I.upload,label:"Upload"},{id:"bookkeeping",icon:I.tax,label:"Kassenbuch"},{id:"export",icon:I.export,label:"Export"},{id:"chat",icon:I.chat,label:"AI Chat"},{id:"help",icon:I.help,label:"Hilfe"}];
  const[hovered,setHovered]=useState(null);
  return(<div style={{width:collapsed?72:248,background:theme.surface,borderRight:`1px solid ${theme.border}`,display:"flex",flexDirection:"column",transition:"width 0.3s cubic-bezier(0.4,0,0.2,1)",flexShrink:0,overflow:"hidden"}}>
    <div style={{padding:collapsed?"20px 16px":"20px 20px",display:"flex",alignItems:"center",gap:12,borderBottom:`1px solid ${theme.border}`,minHeight:77}}>
      <div style={{flexShrink:0}}><ATLogo size={36}/></div>
      {!collapsed&&<div style={{display:"flex",flexDirection:"column",lineHeight:1}}><span style={{fontSize:15,fontWeight:700,color:theme.text,whiteSpace:"nowrap"}}>AutoTax</span><span style={{fontSize:10,fontWeight:800,color:"#00a8cc",letterSpacing:2}}>HUB</span></div>}
    </div>
    <div style={{flex:1,padding:"14px 10px",display:"flex",flexDirection:"column",gap:3}}>
      {items.map(it=>(<div key={it.id} onClick={()=>onNav(it.id)} onMouseEnter={()=>setHovered(it.id)} onMouseLeave={()=>setHovered(null)}
        style={{display:"flex",alignItems:"center",gap:12,padding:collapsed?"11px 16px":"10px 14px",borderRadius:10,cursor:"pointer",
        transition:"all 0.2s cubic-bezier(0.4,0,0.2,1)",
        transitionDelay:hovered===it.id&&active!==it.id?"70ms":"0ms",
        background:active===it.id?theme.accentSoft:hovered===it.id?"rgba(148,163,184,0.06)":"transparent",
        color:active===it.id?theme.accent:hovered===it.id?theme.text:theme.textMuted,
        transform:hovered===it.id&&active!==it.id&&!collapsed?"translateX(3px)":"translateX(0)",
        position:"relative",
        borderLeft:active===it.id?`3px solid ${theme.accent}`:"3px solid transparent"}}>
        <div style={{transition:"transform 0.2s",transform:hovered===it.id&&active!==it.id?"scale(1.1)":"scale(1)"}}><Icon d={it.icon} size={20}/></div>
        {!collapsed&&<span style={{fontSize:14,fontWeight:active===it.id?600:450,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{it.label}</span>}
        {collapsed&&hovered===it.id&&<div style={{position:"absolute",left:64,top:"50%",transform:"translateY(-50%)",background:theme.card,border:"1px solid "+theme.border,borderRadius:8,padding:"8px 14px",whiteSpace:"nowrap",zIndex:100,boxShadow:"0 4px 16px rgba(0,0,0,0.4)"}}>
          <div style={{fontSize:13,fontWeight:600,color:theme.text}}>{it.label}</div>
        </div>}
      </div>))}
    </div>
    <div style={{padding:"12px 10px",borderTop:`1px solid ${theme.border}`}}>
      <div onClick={onLogout} onMouseEnter={e=>e.currentTarget.style.background="rgba(239,68,68,0.08)"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}
        style={{display:"flex",alignItems:"center",gap:12,padding:"10px 14px",borderRadius:10,cursor:"pointer",color:theme.textDim,transition:"all 0.2s"}}>
        <Icon d={I.logout} size={20}/>{!collapsed&&<span style={{fontSize:14}}>Abmelden</span>}
      </div>
    </div>
  </div>);
}
