import { useState, useEffect } from 'react';
import { theme, css, mono } from '../theme';
import { Icon, I, StatCard, BarChart, DonutChart } from '../components/UI';
import api from '../api/client';

export default function DashboardView({refreshKey}){
  const[data,setData]=useState(null);const[loading,setLoading]=useState(true);const[allInv,setAllInv]=useState([]);
  const load=()=>{
    setLoading(true);
    api("/invoices/dashboard?country=DE").then(setData).catch(()=>{}).finally(()=>setLoading(false));
    api("/invoices?limit=100").then(d=>{setAllInv(d.items||[]);}).catch(()=>{});
  };
  useEffect(load,[refreshKey]);

  const resetAll=async()=>{
    if(!confirm("⚠️ ACHTUNG: Alle Rechnungen und Kassenbuch-Einträge werden gelöscht!\n\nDiese Aktion kann NICHT rückgängig gemacht werden.\n\nFortfahren?")) return;
    if(!confirm("Wirklich ALLES löschen? Letzte Warnung!")) return;
    try{
      let delCount=0;
      while(true){
        const invData=await api("/invoices?limit=100").catch(()=>({items:[]}));
        const invoices=invData.items||[];
        if(invoices.length===0) break;
        for(const inv of invoices){try{await api("/invoices/"+inv.id,{method:"DELETE"});delCount++;}catch(e){}}
      }
      let bkCount=0;
      while(true){
        const bkData=await api("/bookkeeping?limit=200").catch(()=>[]);
        const entries=Array.isArray(bkData)?bkData:(bkData.items||[]);
        if(entries.length===0) break;
        for(const e of entries){try{await api("/bookkeeping/"+e.id,{method:"DELETE"});bkCount++;}catch(ex){}}
      }
      alert("Reset abgeschlossen!\n"+delCount+" Rechnungen und "+bkCount+" Kassenbuch-Einträge gelöscht.");
      load();
    }catch(e){alert("Fehler beim Reset: "+e.message);}
  };

  if(loading)return<div style={{display:"flex",alignItems:"center",justifyContent:"center",padding:80,color:theme.textMuted,gap:12}}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={theme.accent} strokeWidth="2" style={{animation:"spin 1s linear infinite"}}><path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.49-8.49l2.83-2.83M2 12h4m12 0h4m-3.93 7.07l-2.83-2.83M7.76 7.76L4.93 4.93"/></svg><span>Dashboard wird geladen...</span></div>;
  if(!data)return<div style={{...css.card,maxWidth:400,margin:"60px auto",textAlign:"center",padding:40}}><div style={{fontSize:28,marginBottom:12}}>⚠️</div><div style={{color:theme.text,fontSize:16,fontWeight:600,marginBottom:6}}>Dashboard nicht verfügbar</div><div style={{color:theme.textMuted,fontSize:13}}>Die Daten konnten nicht geladen werden. Bitte versuche es erneut.</div><button style={{...css.btn(),marginTop:16}} onClick={load}>⟳ Erneut laden</button></div>;
  const si=(data.monthly_breakdown||[]).map(m=>m.income||0);const se=(data.monthly_breakdown||[]).map(m=>m.expenses||0);
  const readCount=allInv.filter(i=>i.total_amount>0).length;const unreadCount=allInv.filter(i=>!i.total_amount||i.total_amount===0).length;
  const totalPct=allInv.length>0?Math.round((readCount/allInv.length)*100):0;
  return(<div style={{display:"flex",flexDirection:"column",gap:28}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",flexWrap:"wrap",gap:12}}>
      <div><h2 style={{fontSize:24,fontWeight:700,color:theme.text,margin:0,letterSpacing:-0.3}}>Dashboard</h2><p style={{color:theme.textMuted,fontSize:13,margin:"6px 0 0",fontWeight:450}}>Übersicht deiner Finanzen</p></div>
      <div style={{display:"flex",gap:8}}>
        <button style={css.btnOutline} onClick={load}>⟳ Aktualisieren</button>
        <button style={{...css.btnOutline,borderColor:"rgba(239,68,68,0.3)",color:theme.danger}} onClick={resetAll}><Icon d={I.reset} size={14} color={theme.danger}/> Zurücksetzen</button>
      </div>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(3, 1fr)",gap:14}}>
      <div style={{...css.card,display:"flex",alignItems:"center",gap:16,padding:"20px 22px",cursor:"default"}}
        onMouseEnter={e=>{e.currentTarget.style.transitionDelay="65ms";e.currentTarget.style.borderColor=theme.accent+"44";e.currentTarget.style.transform="translateY(-2px) scale(1.01)";e.currentTarget.style.boxShadow="0 8px 20px rgba(0,0,0,0.2)";}} onMouseLeave={e=>{e.currentTarget.style.transitionDelay="0ms";e.currentTarget.style.borderColor=theme.border;e.currentTarget.style.transform="translateY(0) scale(1)";e.currentTarget.style.boxShadow="0 1px 3px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.1)";}}>
        <div style={{width:44,height:44,borderRadius:12,background:theme.accentSoft,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,border:`1px solid ${theme.accent}22`}}><Icon d={I.check} size={20} color={theme.accent}/></div>
        <div style={{flex:1}}><div style={{fontSize:12,color:theme.textMuted,marginBottom:3,fontWeight:500}}>Erkannte Belege</div><div style={{fontSize:26,fontWeight:700,color:theme.accent,fontFamily:mono,lineHeight:1}}>{readCount}</div></div>
        <div style={{fontSize:11,color:theme.accent,fontWeight:600,background:theme.accentSoft,padding:"4px 10px",borderRadius:20}}>{totalPct}%</div>
      </div>
      <div style={{...css.card,display:"flex",alignItems:"center",gap:16,padding:"20px 22px",cursor:"default"}}
        onMouseEnter={e=>{e.currentTarget.style.transitionDelay="65ms";e.currentTarget.style.borderColor=theme.warn+"44";e.currentTarget.style.transform="translateY(-2px) scale(1.01)";e.currentTarget.style.boxShadow="0 8px 20px rgba(0,0,0,0.2)";}} onMouseLeave={e=>{e.currentTarget.style.transitionDelay="0ms";e.currentTarget.style.borderColor=theme.border;e.currentTarget.style.transform="translateY(0) scale(1)";e.currentTarget.style.boxShadow="0 1px 3px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.1)";}}>
        <div style={{width:44,height:44,borderRadius:12,background:theme.warnSoft,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,border:`1px solid ${theme.warn}22`}}><Icon d={I.help} size={20} color={theme.warn}/></div>
        <div style={{flex:1}}><div style={{fontSize:12,color:theme.textMuted,marginBottom:3,fontWeight:500}}>Nicht erkannt</div><div style={{fontSize:26,fontWeight:700,color:theme.warn,fontFamily:mono,lineHeight:1}}>{unreadCount}</div></div>
        {unreadCount>0&&<div style={{fontSize:11,color:theme.warn,fontWeight:600,background:theme.warnSoft,padding:"4px 10px",borderRadius:20}}>Prüfen</div>}
      </div>
      <div style={{...css.card,display:"flex",alignItems:"center",gap:16,padding:"20px 22px",cursor:"default"}}
        onMouseEnter={e=>{e.currentTarget.style.transitionDelay="65ms";e.currentTarget.style.borderColor=theme.blue+"44";e.currentTarget.style.transform="translateY(-2px) scale(1.01)";e.currentTarget.style.boxShadow="0 8px 20px rgba(0,0,0,0.2)";}} onMouseLeave={e=>{e.currentTarget.style.transitionDelay="0ms";e.currentTarget.style.borderColor=theme.border;e.currentTarget.style.transform="translateY(0) scale(1)";e.currentTarget.style.boxShadow="0 1px 3px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.1)";}}>
        <div style={{width:44,height:44,borderRadius:12,background:theme.blueSoft,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,border:`1px solid ${theme.blue}22`}}><Icon d={I.invoice} size={20} color={theme.blue}/></div>
        <div style={{flex:1}}><div style={{fontSize:12,color:theme.textMuted,marginBottom:3,fontWeight:500}}>Gesamt Belege</div><div style={{fontSize:26,fontWeight:700,color:theme.blue,fontFamily:mono,lineHeight:1}}>{allInv.length}</div></div>
      </div>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit, minmax(240px, 1fr))",gap:14}}>
      <StatCard label="Einnahmen" value={"€"+data.total_income?.toLocaleString("de-DE",{minimumFractionDigits:2})} icon={I.trend} color={theme.accent} bgColor={theme.accentSoft} sparkData={si} sub={data.income_count+" Rechnungen"}/>
      <StatCard label="Ausgaben" value={"€"+data.total_expenses?.toLocaleString("de-DE",{minimumFractionDigits:2})} icon={I.down} color={theme.danger} bgColor={theme.dangerSoft} sparkData={se} sub={data.expense_count+" Rechnungen"}/>
      <StatCard label="Gewinn" value={"€"+data.net_profit?.toLocaleString("de-DE",{minimumFractionDigits:2})} icon={I.dashboard} color={data.net_profit>=0?theme.accent:theme.danger} bgColor={data.net_profit>=0?theme.accentSoft:theme.dangerSoft}/>
      <StatCard label="Steuer (geschätzt)" value={"€"+data.tax_estimate?.toLocaleString("de-DE",{minimumFractionDigits:2})} icon={I.tax} color={theme.purple} bgColor={theme.purpleSoft} sub={data.tax_rate_applied+"% eff. Steuersatz"}/>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"5fr 3fr",gap:14}}>
      <div style={css.card}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20}}><h3 style={{fontSize:15,fontWeight:600,color:theme.text,margin:0}}>Monatliche Übersicht</h3><span style={{fontSize:11,color:theme.textDim,fontFamily:mono}}>{new Date().getFullYear()}</span></div>{data.monthly_breakdown?.length>0?<BarChart data={data.monthly_breakdown}/>:<div style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:40,color:theme.textDim}}><Icon d={I.trend} size={32} color={theme.textDim}/><p style={{fontSize:13,marginTop:10}}>Noch keine Daten</p></div>}</div>
      <div style={css.card}><h3 style={{fontSize:15,fontWeight:600,color:theme.text,margin:"0 0 20px"}}>Kategorien</h3>{data.by_category?.length>0?<DonutChart data={data.by_category}/>:<div style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:40,color:theme.textDim}}><Icon d={I.tax} size={32} color={theme.textDim}/><p style={{fontSize:13,marginTop:10}}>Keine Kategorien</p></div>}</div>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <div style={css.card}><h3 style={{fontSize:15,fontWeight:600,color:theme.text,margin:"0 0 16px",display:"flex",alignItems:"center",gap:8}}><div style={{width:6,height:6,borderRadius:"50%",background:theme.blue}}/>MwSt Übersicht</h3>
        <div style={{display:"flex",flexDirection:"column",gap:12}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><span style={{color:theme.textMuted,fontSize:13}}>Gezahlte Vorsteuer</span><span style={{color:theme.text,fontFamily:mono,fontSize:14,fontWeight:500}}>€{data.total_vat_paid?.toFixed(2)}</span></div>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><span style={{color:theme.textMuted,fontSize:13}}>Vereinnahmte USt</span><span style={{color:theme.text,fontFamily:mono,fontSize:14,fontWeight:500}}>€{data.total_vat_collected?.toFixed(2)}</span></div>
          <div style={{height:1,background:theme.border,margin:"2px 0"}}/>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><span style={{color:theme.text,fontSize:14,fontWeight:600}}>Saldo</span><span style={{color:data.vat_balance>=0?theme.danger:theme.accent,fontFamily:mono,fontSize:17,fontWeight:700}}>€{data.vat_balance?.toFixed(2)}</span></div>
        </div>
      </div>
      <div style={css.card}><h3 style={{fontSize:15,fontWeight:600,color:theme.text,margin:"0 0 16px",display:"flex",alignItems:"center",gap:8}}><div style={{width:6,height:6,borderRadius:"50%",background:theme.purple}}/>Gesamt</h3>
        <div style={{display:"flex",flexDirection:"column",gap:12}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><span style={{color:theme.textMuted,fontSize:13}}>Rechnungen</span><span style={{color:theme.text,fontFamily:mono,fontSize:14,fontWeight:600}}>{data.invoice_count}</span></div>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><div style={{display:"flex",alignItems:"center",gap:6}}><span style={{display:"inline-block",width:8,height:8,borderRadius:"50%",background:theme.accent}}></span><span style={{color:theme.textMuted,fontSize:13}}>Einnahmen</span></div><span style={{color:theme.accent,fontFamily:mono,fontSize:14,fontWeight:600}}>{data.income_count}</span></div>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><div style={{display:"flex",alignItems:"center",gap:6}}><span style={{display:"inline-block",width:8,height:8,borderRadius:"50%",background:theme.danger}}></span><span style={{color:theme.textMuted,fontSize:13}}>Ausgaben</span></div><span style={{color:theme.danger,fontFamily:mono,fontSize:14,fontWeight:600}}>{data.expense_count}</span></div>
          {data.invoice_count>0&&<div style={{height:6,background:theme.surfaceAlt,borderRadius:3,overflow:"hidden",marginTop:4}}>
            <div style={{height:"100%",width:`${(data.income_count/(data.invoice_count||1))*100}%`,background:`linear-gradient(90deg, ${theme.accent}, ${theme.accent}bb)`,borderRadius:3,transition:"width 0.6s ease"}}/>
          </div>}
        </div>
      </div>
    </div>
  </div>);
}
