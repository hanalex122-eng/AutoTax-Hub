import React from 'react';
import { theme, mono } from '../theme';

export const Icon = React.memo(({d,size=20,color="currentColor"})=>(
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" style={{animation:"iconIn 0.15s ease-out"}}><path d={d}/></svg>
));

export const I = {
  dashboard:"M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4",
  invoice:"M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  upload:"M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12",
  export:"M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  tax:"M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z",
  chat:"M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z",
  logout:"M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1",
  user:"M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z",
  trend:"M13 7h8m0 0v8m0-8l-8 8-4-4-6 6",down:"M19 14l-7 7m0 0l-7-7m7 7V3",
  check:"M5 13l4 4L19 7",x:"M6 18L18 6M6 6l12 12",menu:"M4 6h16M4 12h16M4 18h16",
  search:"M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  reset:"M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",
  trash:"M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16",
  help:"M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3m.08 4h.01M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z",
};

export function ATLogo({size=36}){return(
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
    <rect width="100" height="100" rx="18" fill="#0f1c2e"/>
    <text x="10" y="52" fontFamily="Arial Black" fontWeight="900" fontSize="46" fill="#1e3a5f">A</text>
    <text x="38" y="52" fontFamily="Arial Black" fontWeight="900" fontSize="46" fill="#1e3a5f">T</text>
    <polyline points="14,76 28,66 40,70 52,60 64,64 80,42" stroke="#00a8cc" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
    <polygon points="80,42 80,52 70,45" fill="#00a8cc"/>
    <text x="50" y="88" textAnchor="middle" fontFamily="Arial" fontWeight="700" fontSize="12" fill="#c0d0e0">AutoTax</text>
    <text x="50" y="97" textAnchor="middle" fontFamily="Arial Black" fontWeight="900" fontSize="10" fill="#00a8cc" letterSpacing="3">HUB</text>
  </svg>
);}

export function Sparkline({data=[],color=theme.accent,h=40,w=120}){
  if(!data.length)return null;
  const max=Math.max(...data,1);
  const pts=data.map((v,i)=>`${(i/(data.length-1))*w},${h-(v/max)*h}`).join(" ");
  return(<svg width={w} height={h} style={{overflow:"visible"}}><polyline points={pts} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"/></svg>);
}

export function StatCard({label,value,sub,icon,color,bgColor,sparkData}){return(
  <div style={{...cssCard,display:"flex",flexDirection:"column",gap:14,position:"relative",overflow:"hidden",cursor:"default"}}
    onMouseEnter={e=>{e.currentTarget.style.transitionDelay="65ms";e.currentTarget.style.transform="translateY(-3px) scale(1.015)";e.currentTarget.style.boxShadow=`0 12px 28px rgba(0,0,0,0.25), 0 0 0 1px ${color}22`;}}
    onMouseLeave={e=>{e.currentTarget.style.transitionDelay="0ms";e.currentTarget.style.transform="translateY(0) scale(1)";e.currentTarget.style.boxShadow="0 1px 3px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.1)";}}>
    <div style={{position:"absolute",top:-30,right:-30,width:110,height:110,borderRadius:"50%",background:bgColor,opacity:0.25,filter:"blur(8px)",transition:"opacity 0.2s"}}/>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",position:"relative"}}>
      <div style={{width:42,height:42,borderRadius:11,background:bgColor,display:"flex",alignItems:"center",justifyContent:"center",border:`1px solid ${color}22`}}><Icon d={icon} size={20} color={color}/></div>
      {sparkData&&<Sparkline data={sparkData} color={color}/>}
    </div>
    <div style={{position:"relative"}}>
      <div style={{fontSize:26,fontWeight:700,color:theme.text,fontFamily:mono,letterSpacing:-1,lineHeight:1.2}}>{value}</div>
      <div style={{fontSize:13,color:theme.textMuted,marginTop:4,fontWeight:500}}>{label}</div>
      {sub&&<div style={{fontSize:12,color,marginTop:6,fontWeight:500,display:"flex",alignItems:"center",gap:4}}>
        <span style={{display:"inline-block",width:6,height:6,borderRadius:"50%",background:color,opacity:0.7}}></span>{sub}
      </div>}
    </div>
  </div>
);}

const cssCard = { background:theme.card,borderRadius:14,border:`1px solid ${theme.border}`,padding:24,boxShadow:"0 1px 3px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.1)",transition:"box-shadow 0.2s cubic-bezier(0.4,0,0.2,1), transform 0.2s cubic-bezier(0.4,0,0.2,1), border-color 0.2s ease" };

export function BarChart({data}){
  const mx=Math.max(...data.flatMap(d=>[d.income||0,d.expenses||0]),1);
  const monthNames=["","Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"];
  return(<div style={{display:"flex",flexDirection:"column",gap:8}}>
    <div style={{display:"flex",gap:20,marginBottom:12}}>
      <div style={{display:"flex",alignItems:"center",gap:8}}><div style={{width:12,height:4,borderRadius:2,background:theme.accent}}/><span style={{fontSize:12,color:theme.textMuted,fontWeight:500}}>Einnahmen</span></div>
      <div style={{display:"flex",alignItems:"center",gap:8}}><div style={{width:12,height:4,borderRadius:2,background:theme.danger}}/><span style={{fontSize:12,color:theme.textMuted,fontWeight:500}}>Ausgaben</span></div>
    </div>
    <div style={{display:"flex",alignItems:"flex-end",gap:6,height:180,padding:"0 4px"}}>
      {data.map((d,i)=>{const mNum=parseInt(d.month?.slice(5)||"0",10);return(<div key={i} style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",gap:2}}>
        <div style={{display:"flex",gap:3,alignItems:"flex-end",height:155,width:"100%"}}>
          <div style={{flex:1,background:`linear-gradient(180deg, ${theme.accent} 0%, ${theme.accent}99 100%)`,borderRadius:"5px 5px 1px 1px",height:`${((d.income||0)/mx)*100}%`,minHeight:3,transition:"height 0.6s cubic-bezier(0.4,0,0.2,1)"}} title={`Einnahmen: €${(d.income||0).toFixed(2)}`}/>
          <div style={{flex:1,background:`linear-gradient(180deg, ${theme.danger} 0%, ${theme.danger}99 100%)`,borderRadius:"5px 5px 1px 1px",height:`${((d.expenses||0)/mx)*100}%`,minHeight:3,transition:"height 0.6s cubic-bezier(0.4,0,0.2,1)"}} title={`Ausgaben: €${(d.expenses||0).toFixed(2)}`}/>
        </div>
        <div style={{fontSize:11,color:theme.textDim,marginTop:6,fontWeight:500}}>{monthNames[mNum]||d.month?.slice(5)||""}</div>
      </div>);})}
    </div>
  </div>);
}

export function DonutChart({data}){
  const total=data.reduce((s,d)=>s+d.total,0)||1;
  const colors=[theme.accent,theme.blue,theme.purple,theme.warn,theme.danger,"#06b6d4","#ec4899","#84cc16"];
  let cum=0;
  return(<div style={{display:"flex",alignItems:"center",gap:28}}>
    <svg width={110} height={110} viewBox="0 0 42 42" style={{flexShrink:0}}>
      <circle cx={21} cy={21} r={15.9} fill="none" stroke={theme.surfaceAlt} strokeWidth={4.5}/>
      {data.slice(0,8).map((d,i)=>{const pct=(d.total/total)*100;const off=25-cum;cum+=pct;return<circle key={i} cx={21} cy={21} r={15.9} fill="none" stroke={colors[i%colors.length]} strokeWidth={4.5} strokeDasharray={`${pct} ${100-pct}`} strokeDashoffset={off} style={{transition:"stroke-dasharray 0.6s ease"}}/>;})
      }
      <text x="21" y="19" textAnchor="middle" dy=".35em" fill={theme.text} fontSize="7" fontWeight="700" fontFamily={mono}>{data.length}</text>
      <text x="21" y="26" textAnchor="middle" fill={theme.textDim} fontSize="3.5" fontFamily="'DM Sans', system-ui, sans-serif">Kategorien</text>
    </svg>
    <div style={{display:"flex",flexDirection:"column",gap:8,flex:1}}>
      {data.slice(0,6).map((d,i)=>(<div key={i} style={{display:"flex",alignItems:"center",gap:10,fontSize:12}}>
        <div style={{width:8,height:8,borderRadius:"50%",background:colors[i%colors.length],flexShrink:0,boxShadow:`0 0 6px ${colors[i%colors.length]}44`}}/>
        <span style={{color:theme.textMuted,flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",fontWeight:450}}>{d.category}</span>
        <span style={{color:theme.text,fontWeight:600,fontFamily:mono,fontSize:12}}>€{d.total?.toFixed(0)}</span>
      </div>))}
    </div>
  </div>);
}
