"""Private pilot browser interface for MACIE B."""
PAGE_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MACIE B | Prompt Consensus</title>
<style>
:root{color-scheme:dark;--bg:#09111c;--panel:#101d2d;--line:#29415e;--text:#edf4ff;--muted:#9fb0c5;--accent:#4fd1c5;--bad:#ff8f8f}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(145deg,#07101a,#0b1624);color:var(--text);font:16px system-ui,sans-serif}
main{max-width:860px;margin:auto;padding:32px 18px 70px}.brand{color:var(--accent);font-weight:800;letter-spacing:.12em}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:22px;margin:18px 0;box-shadow:0 18px 45px #0005}
h1{font-size:clamp(2rem,7vw,3.4rem);margin:.35rem 0}h2{margin-top:0}p{color:var(--muted);line-height:1.55}
label{display:block;margin:14px 0 6px}input,textarea,button{width:100%;font:inherit;border-radius:10px;padding:12px}
input,textarea{background:#07111d;color:var(--text);border:1px solid var(--line)}textarea{min-height:190px;resize:vertical}
button{border:0;background:var(--accent);color:#041016;font-weight:800;margin-top:14px;cursor:pointer}
button.secondary{background:#20334a;color:var(--text)}button:disabled{opacity:.55}.hide{display:none}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#07111d;border:1px solid var(--line);padding:16px;border-radius:10px;line-height:1.45}
.notice{font-size:.9rem;color:var(--muted)}.error{color:var(--bad)}
</style></head><body><main>
<div class="brand">ACTIONFORGE LABS · PRIVATE PILOT</div>
<h1>MACIE B</h1>
<p>Prompt consensus. Paste a prompt created anywhere. Independent Claude and ChatGPT reviews are reconciled into one improved prompt. MACIE A private SageForge context is never loaded.</p>
{% if not email %}
<section class="card"><h2>Sign in</h2>
<form id="loginForm"><label>Email<input name="email" type="email" autocomplete="username" required></label>
<label>Password<input name="password" type="password" autocomplete="current-password" required></label>
<button type="submit">Sign in securely</button></form><p id="loginStatus" class="notice"></p></section>
{% else %}
<section class="card"><h2>Authorized account</h2><p>{{ email }}</p>
<button id="logout" class="secondary">Sign out</button></section>
<section class="card"><h2>1. Connect your provider</h2>
<p>Your own OpenRouter key supplies both independent model lanes for this signed-in session.</p>
<form id="providerForm"><label>OpenRouter API key<input name="api_key" type="password" autocomplete="off" required></label>
<button type="submit">Connect or replace key</button></form>
<button id="disconnect" class="secondary">Delete session key</button><p id="providerStatus" class="notice"></p></section>
<section class="card"><h2>2. Improve a prompt</h2>
<form id="promptForm"><label>Original prompt<textarea name="prompt" maxlength="20000" required placeholder="Paste a prompt created in any application..."></textarea></label>
<button type="submit">Run Claude + ChatGPT consensus</button></form>
<p id="jobStatus" class="notice"></p><pre id="output" class="hide"></pre></section>
{% endif %}
<p class="notice">MACIE B private operational pilot · Buyer-key architecture · No automatic publication</p>
</main>
<script nonce="{{ nonce }}">
const csrf={{ csrf|tojson }};
const byId=id=>document.getElementById(id);
async function call(path,method="GET",body){
 const headers={}; if(body!==undefined)headers["Content-Type"]="application/json";
 if(method!=="GET")headers["X-CSRF-Token"]=csrf;
 const response=await fetch("/macie/b"+path,{method,headers,credentials:"same-origin",body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json().catch(()=>({error:"Unexpected server response."}));
 if(!response.ok)throw new Error(data.error||"Request failed.");
 return data;
}
const login=byId("loginForm");
if(login)login.addEventListener("submit",async e=>{e.preventDefault();try{byId("loginStatus").textContent="Signing in...";await call("/login","POST",{email:login.elements.email.value,password:login.elements.password.value});location.reload();}catch(err){byId("loginStatus").textContent=err.message;byId("loginStatus").className="error";}});
const logout=byId("logout");if(logout)logout.onclick=async()=>{await call("/logout","POST",{});location.reload();};
const provider=byId("providerForm");
async function refreshProvider(){try{const s=await call("/provider");byId("providerStatus").textContent=s.connected?"Provider connected for this session.":"Connect your OpenRouter key to continue.";}catch(err){byId("providerStatus").textContent=err.message;}}
if(provider){refreshProvider();provider.addEventListener("submit",async e=>{e.preventDefault();try{await call("/provider","POST",{api_key:provider.elements.api_key.value});provider.reset();await refreshProvider();}catch(err){byId("providerStatus").textContent=err.message;}});}
const disconnect=byId("disconnect");if(disconnect)disconnect.onclick=async()=>{await call("/provider","DELETE",{});await refreshProvider();};
const promptForm=byId("promptForm");
if(promptForm)promptForm.addEventListener("submit",async e=>{e.preventDefault();const button=promptForm.querySelector("button");button.disabled=true;byId("output").classList.add("hide");try{
 byId("jobStatus").textContent="Submitting prompt...";
 const job=await call("/enhance","POST",{prompt:promptForm.elements.prompt.value});
 for(let i=0;i<60;i++){await new Promise(resolve=>setTimeout(resolve,2000));const state=await call("/enhance/"+encodeURIComponent(job.job_id));
  if(state.status==="queued"||state.status==="running"){byId("jobStatus").textContent="Claude and ChatGPT are reviewing...";continue;}
  if(state.status==="finished"){byId("jobStatus").textContent="Consensus complete.";byId("output").textContent=JSON.stringify(state.result,null,2);byId("output").classList.remove("hide");return;}
  throw new Error(state.error||"Consensus failed.");
 }
 byId("jobStatus").textContent="Still processing. Keep this page open.";
}catch(err){byId("jobStatus").textContent=err.message;byId("jobStatus").className="error";}finally{button.disabled=false;}});
</script></body></html>"""
