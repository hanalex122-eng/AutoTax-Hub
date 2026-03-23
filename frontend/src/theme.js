export const theme = {
  bg: "#0a0e17", surface: "#111827", surfaceAlt: "#1a2234", card: "#1e293b",
  border: "#2a3548", accent: "#10b981", accentSoft: "rgba(16,185,129,0.12)",
  danger: "#ef4444", dangerSoft: "rgba(239,68,68,0.12)", warn: "#f59e0b",
  warnSoft: "rgba(245,158,11,0.12)", blue: "#3b82f6", blueSoft: "rgba(59,130,246,0.12)",
  purple: "#8b5cf6", purpleSoft: "rgba(139,92,246,0.12)",
  text: "#f1f5f9", textMuted: "#94a3b8", textDim: "#64748b",
};

export const font = "'DM Sans', system-ui, sans-serif";
export const mono = "'JetBrains Mono', monospace";

export const css = {
  input: { width:"100%",padding:"11px 14px",background:theme.surfaceAlt,border:`1.5px solid ${theme.border}`,borderRadius:10,color:theme.text,fontSize:14,fontFamily:font,outline:"none",transition:"border 0.2s, box-shadow 0.2s",boxSizing:"border-box" },
  btn: (c=theme.accent)=>({ padding:"10px 22px",background:c,color:"#fff",border:"none",borderRadius:10,fontSize:14,fontWeight:600,cursor:"pointer",fontFamily:font,transition:"all 0.2s cubic-bezier(0.4,0,0.2,1)",display:"inline-flex",alignItems:"center",gap:8,boxShadow:`0 2px 8px ${c}33` }),
  btnOutline: { padding:"10px 20px",background:"transparent",border:`1.5px solid ${theme.border}`,borderRadius:10,color:theme.textMuted,fontSize:13,fontWeight:500,cursor:"pointer",fontFamily:font,transition:"all 0.2s cubic-bezier(0.4,0,0.2,1)" },
  card: { background:theme.card,borderRadius:14,border:`1px solid ${theme.border}`,padding:24,boxShadow:"0 1px 3px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.1)",transition:"box-shadow 0.2s cubic-bezier(0.4,0,0.2,1), transform 0.2s cubic-bezier(0.4,0,0.2,1), border-color 0.2s ease" },
  badge: (bg,c)=>({ padding:"4px 10px",borderRadius:20,fontSize:11,fontWeight:600,background:bg,color:c,letterSpacing:0.3,display:"inline-block" }),
};

export function formatDateEU(dateStr) {
  if (!dateStr) return "—";
  const iso = /^(\d{4})-(\d{2})-(\d{2})/;
  const m1 = dateStr.match(iso);
  if (m1) return m1[3] + "." + m1[2] + "." + m1[1];
  const us = /^(\d{1,2})\/(\d{1,2})\/(\d{4})/;
  const m2 = dateStr.match(us);
  if (m2) return m2[2].padStart(2,"0") + "." + m2[1].padStart(2,"0") + "." + m2[3];
  if (/^\d{2}\.\d{2}\.\d{4}$/.test(dateStr)) return dateStr;
  return dateStr;
}
