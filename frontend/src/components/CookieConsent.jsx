import { useState } from 'react';
import { theme, css, font } from '../theme';

export default function CookieConsent(){
  const[visible,setVisible]=useState(!localStorage.getItem("atx_cookie_consent"));
  if(!visible)return null;
  return(<div style={{position:"fixed",bottom:0,left:0,right:0,zIndex:2000,background:theme.surface,borderTop:"1px solid "+theme.border,padding:"16px 24px",display:"flex",alignItems:"center",justifyContent:"space-between",gap:16,flexWrap:"wrap",fontFamily:font}}>
    <div style={{flex:1,minWidth:280}}><div style={{fontSize:14,fontWeight:600,color:theme.text,marginBottom:4}}>🔒 Datenschutz & Cookies</div><div style={{fontSize:12,color:theme.textMuted,lineHeight:1.5}}>Nur technisch notwendige Cookies. Kein Tracking. DSGVO-konform.</div></div>
    <div style={{display:"flex",gap:10}}>
      <button style={css.btnOutline} onClick={()=>{localStorage.setItem("atx_cookie_consent","declined");setVisible(false);}}>Nur notwendige</button>
      <button style={css.btn()} onClick={()=>{localStorage.setItem("atx_cookie_consent","accepted");setVisible(false);}}>Akzeptieren</button>
    </div>
  </div>);
}
