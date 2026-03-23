import { useState, useRef, Fragment } from 'react';
import { theme, css, font } from '../theme';
import { Icon, I, ATLogo } from '../components/UI';
import api from '../api/client';

export default function AuthScreen({onLogin}){
  const[mode,setMode]=useState("login");
  const[email,setEmail]=useState("");
  const[password,setPassword]=useState("");
  const[name,setName]=useState("");
  const[error,setError]=useState("");
  const[info,setInfo]=useState("");
  const[loading,setLoading]=useState(false);
  const[gdpr,setGdpr]=useState(false);
  const[showPass,setShowPass]=useState(false);
  const[showDS,setShowDS]=useState(false);
  const[showImp,setShowImp]=useState(false);
  const emailRef=useRef(null);
  const passRef=useRef(null);
  const nameRef=useRef(null);

  const submit=async()=>{
    setError("");setInfo("");
    const realEmail=(emailRef.current?.value||email).trim();
    const realPass=passRef.current?.value||password;
    const realName=(nameRef.current?.value||name).trim();
    setEmail(realEmail);setPassword(realPass);setName(realName);

    if(!realEmail||!realPass){setError("Bitte E-Mail und Passwort eingeben.");return;}
    if(!realEmail.includes("@")){setError("Bitte eine gültige E-Mail-Adresse eingeben.");return;}
    if(mode==="register"&&!gdpr){setError("Bitte Datenschutzerklärung akzeptieren.");return;}
    if(mode==="register"&&!realName){setError("Bitte vollständigen Namen eingeben.");return;}
    if(mode==="register"&&realPass.length<6){setError("Passwort muss mindestens 6 Zeichen lang sein.");return;}
    setLoading(true);
    try{
      if(mode==="register"){
        await api("/auth/register",{method:"POST",body:JSON.stringify({email:realEmail,password:realPass,full_name:realName})});
        setMode("login");setError("");setPassword("");
        setInfo("Konto erstellt! Bitte jetzt mit deinen Daten einloggen.");
      }else{
        const data=await api("/auth/login",{method:"POST",body:JSON.stringify({email:realEmail,password:realPass})});
        localStorage.setItem("atx_token",data.data?.token||data.access_token);
        if(data.data?.refresh_token||data.refresh_token) localStorage.setItem("atx_refresh",data.data?.refresh_token||data.refresh_token);
        onLogin();
      }
    }catch(e){
      const msg=e.message||"";
      if(msg.includes("Failed to fetch")||msg.includes("NetworkError")||msg.includes("ERR_")||msg.includes("Load failed")){
        setError("Server nicht erreichbar. Prüfe deine Internetverbindung oder versuche es in 1-2 Minuten erneut. (Der Server startet evtl. gerade neu)");
      }else if(msg.includes("special character")){
        setError("Passwort muss mindestens 1 Sonderzeichen enthalten (z.B. ! @ # $ % & *)");
      }else if(msg.includes("uppercase")){
        setError("Passwort muss mindestens 1 Großbuchstaben enthalten.");
      }else if(msg.includes("digit")||msg.includes("number")){
        setError("Passwort muss mindestens 1 Zahl enthalten.");
      }else if(msg.includes("Password")||msg.includes("password")){
        setError("Passwort-Anforderungen: min. 6 Zeichen, 1 Großbuchstabe, 1 Zahl, 1 Sonderzeichen (! @ # $ % & *)");
      }else if(msg.includes("unauthorized")||msg.includes("401")||msg.includes("Invalid")||msg.includes("invalid")){
        setError("E-Mail oder Passwort falsch.");
      }else if(msg.includes("already")||msg.includes("exists")||msg.includes("duplicate")){
        setError("Diese E-Mail ist bereits registriert. Bitte auf 'Anmelden' klicken.");
      }else if(msg.includes("validation")||msg.includes("422")||msg.includes("value_error")){
        setError("Ungültige Eingabe. Passwort: min. 6 Zeichen, 1 Großbuchstabe, 1 Zahl, 1 Sonderzeichen.");
      }else{
        setError(msg||"Ein Fehler ist aufgetreten. Bitte versuche es erneut.");
      }
    }
    setLoading(false);
  };

  return(<div style={{minHeight:"100vh",background:theme.bg,display:"flex",alignItems:"center",justifyContent:"center",fontFamily:font,padding:20}}>
    <div style={{position:"fixed",inset:0,background:"radial-gradient(ellipse at 30% 20%, rgba(16,185,129,0.08) 0%, transparent 60%), radial-gradient(ellipse at 70% 80%, rgba(59,130,246,0.06) 0%, transparent 60%)"}}/>
    <div style={{...css.card,width:420,maxWidth:"100%",position:"relative",padding:40}}>
      <div style={{textAlign:"center",marginBottom:32}}>
        <div style={{display:"inline-flex",marginBottom:16}}><ATLogo size={64}/></div>
        <h1 style={{fontSize:24,fontWeight:700,color:theme.text,margin:0}}>AutoTax-<span style={{color:"#00a8cc"}}>HUB</span></h1>
        <p style={{color:theme.textMuted,fontSize:14,margin:"8px 0 0"}}>{mode==="login"?"Willkommen zurück":"Neues Konto erstellen"}</p>
      </div>
      {mode==="register"&&<div style={{marginBottom:16}}><label style={{fontSize:12,color:theme.textMuted,marginBottom:6,display:"block",fontWeight:500}}>Vollständiger Name</label><input ref={nameRef} style={css.input} value={name} onChange={e=>setName(e.target.value)} placeholder="Max Mustermann"/></div>}
      <div style={{marginBottom:16}}><label style={{fontSize:12,color:theme.textMuted,marginBottom:6,display:"block",fontWeight:500}}>E-Mail</label><input ref={emailRef} style={css.input} type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="email@beispiel.de"/></div>
      <div style={{marginBottom:24}}><label style={{fontSize:12,color:theme.textMuted,marginBottom:6,display:"block",fontWeight:500}}>Passwort</label><div style={{position:"relative"}}><input ref={passRef} style={{...css.input,paddingRight:44}} type={showPass?"text":"password"} value={password} onChange={e=>setPassword(e.target.value)} placeholder="••••••••" onKeyDown={e=>e.key==="Enter"&&submit()}/><div onClick={()=>setShowPass(!showPass)} style={{position:"absolute",right:12,top:"50%",transform:"translateY(-50%)",cursor:"pointer",padding:4,opacity:0.6}}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={theme.textMuted} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{showPass?<Fragment><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></Fragment>:<Fragment><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></Fragment>}</svg></div></div>
      {mode==="register"&&<div style={{fontSize:11,color:theme.textDim,marginTop:6}}>Min. 6 Zeichen, 1 Großbuchstabe, 1 Zahl, 1 Sonderzeichen (! @ # $ %)</div>}</div>
      {mode==="register"&&<div style={{marginBottom:20,display:"flex",alignItems:"flex-start",gap:10}}>
        <input type="checkbox" checked={gdpr} onChange={e=>setGdpr(e.target.checked)} style={{marginTop:3,width:18,height:18,accentColor:theme.accent,cursor:"pointer",flexShrink:0}}/>
        <span style={{fontSize:12,color:theme.textMuted,lineHeight:1.5}}>Ich habe die <span style={{color:theme.accent,cursor:"pointer",textDecoration:"underline"}} onClick={()=>setShowDS(true)}>Datenschutzerklärung</span> gelesen und akzeptiere die Verarbeitung meiner Daten gemäß DSGVO.</span>
      </div>}
      {info&&<div style={{background:theme.accentSoft,color:theme.accent,marginBottom:16,padding:"10px 14px",borderRadius:10,fontSize:13}}>{info}</div>}
      {error&&<div style={{background:theme.dangerSoft,color:theme.danger,marginBottom:16,padding:"10px 14px",borderRadius:10,fontSize:13}}>{error}</div>}
      <button style={{...css.btn(),width:"100%",justifyContent:"center",opacity:loading?0.7:1}} onClick={submit} disabled={loading}>{loading?"...":mode==="login"?"Anmelden":"Registrieren"}</button>
      <div style={{textAlign:"center",marginTop:20}}>
        <span style={{color:theme.textDim,fontSize:13}}>{mode==="login"?"Noch kein Konto? ":"Bereits registriert? "}</span>
        <span style={{color:theme.accent,fontSize:13,fontWeight:600,cursor:"pointer"}} onClick={()=>{setMode(mode==="login"?"register":"login");setError("");}}>{mode==="login"?"Registrieren":"Anmelden"}</span>
      </div>
      <div style={{display:"flex",justifyContent:"center",gap:16,marginTop:20,paddingTop:16,borderTop:`1px solid ${theme.border}`}}>
        <span style={{fontSize:11,color:theme.textDim,cursor:"pointer",textDecoration:"underline"}} onClick={()=>setShowDS(true)}>Datenschutz</span>
        <span style={{fontSize:11,color:theme.textDim,cursor:"pointer",textDecoration:"underline"}} onClick={()=>setShowImp(true)}>Impressum</span>
      </div>
    </div>
    {showDS&&<div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.7)",zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center",padding:20}} onClick={()=>setShowDS(false)}>
      <div style={{...css.card,maxWidth:640,maxHeight:"80vh",overflowY:"auto",padding:32}} onClick={e=>e.stopPropagation()}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20}}><h2 style={{fontSize:20,fontWeight:700,color:theme.text,margin:0}}>Datenschutzerklärung</h2><div style={{cursor:"pointer"}} onClick={()=>setShowDS(false)}><Icon d={I.x} size={20} color={theme.textMuted}/></div></div>
        <div style={{fontSize:13,color:theme.textMuted,lineHeight:1.8}}>
          <h3 style={{color:theme.text,fontSize:15,margin:"16px 0 8px"}}>1. Verantwortlicher</h3><p>AutoTax-HUB — autotaxhub.de / datenschutz@autotaxhub.de</p>
          <h3 style={{color:theme.text,fontSize:15,margin:"16px 0 8px"}}>2. Erhobene Daten</h3><p>Name, E-Mail, Rechnungsdaten, hochgeladene Dokumente, IP-Adresse.</p>
          <h3 style={{color:theme.text,fontSize:15,margin:"16px 0 8px"}}>3. Rechtsgrundlage</h3><p>Art. 6 Abs. 1 lit. a (Einwilligung), lit. b (Vertragserfüllung), lit. f (berechtigte Interessen) DSGVO.</p>
          <h3 style={{color:theme.text,fontSize:15,margin:"16px 0 8px"}}>4. Zweck</h3><p>Rechnungsverwaltung, Steuerberechnung, DATEV-Export, AI-Kategorisierung.</p>
          <h3 style={{color:theme.text,fontSize:15,margin:"16px 0 8px"}}>5. Hosting</h3><p>Server: Railway (EU). TLS/SSL verschlüsselt.</p>
          <h3 style={{color:theme.text,fontSize:15,margin:"16px 0 8px"}}>6. AI-Verarbeitung</h3><p>Anonymisierte Daten an Anthropic Claude API. Keine personenbezogenen Daten an Dritte.</p>
          <h3 style={{color:theme.text,fontSize:15,margin:"16px 0 8px"}}>7. Ihre Rechte (Art. 15-21)</h3><p>Auskunft, Berichtigung, Löschung, Einschränkung, Datenübertragbarkeit, Widerspruch.</p>
          <h3 style={{color:theme.text,fontSize:15,margin:"16px 0 8px"}}>8. Cookies</h3><p>Nur technisch notwendige Cookies. Kein Tracking.</p>
          <p style={{fontSize:12,color:theme.textDim,marginTop:16}}>Stand: März 2026</p>
        </div>
      </div>
    </div>}
    {showImp&&<div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.7)",zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center",padding:20}} onClick={()=>setShowImp(false)}>
      <div style={{...css.card,maxWidth:500,padding:32}} onClick={e=>e.stopPropagation()}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20}}><h2 style={{fontSize:20,fontWeight:700,color:theme.text,margin:0}}>Impressum</h2><div style={{cursor:"pointer"}} onClick={()=>setShowImp(false)}><Icon d={I.x} size={20} color={theme.textMuted}/></div></div>
        <div style={{fontSize:13,color:theme.textMuted,lineHeight:1.8}}>
          <p><strong style={{color:theme.text}}>AutoTax-HUB</strong> — Angaben gemäß § 5 TMG</p>
          <p>Betreiber: [Ihr Name]<br/>Adresse: [Ihre Adresse]<br/>E-Mail: info@autotaxhub.de</p>
          <p><strong style={{color:theme.text}}>Haftungshinweis:</strong> Steuerberechnungen dienen nur als Schätzung.</p>
        </div>
      </div>
    </div>}
  </div>);
}
