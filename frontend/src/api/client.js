const API = "https://1k2d2t5n.up.railway.app";

export { API };

export default async function api(path, opts={}) {
  const token = localStorage.getItem("atx_token");
  const headers = {"Content-Type":"application/json",...opts.headers};
  if(token) headers["Authorization"]=`Bearer ${token}`;
  const res = await fetch(`${API}${path}`,{...opts,headers});
  if(res.status===401){localStorage.removeItem("atx_token");throw new Error("unauthorized");}
  if(!res.ok){const e=await res.json().catch(()=>({}));const msg=typeof e.detail==="string"?e.detail:typeof e.detail==="object"?JSON.stringify(e.detail):e.message||"Error";throw new Error(msg);}
  if(res.status===204) return null;
  return res.json();
}
