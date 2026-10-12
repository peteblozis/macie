"""Standalone no-dependency MACIE C browser interface.

The source and results stay in browser memory until the operator downloads
them. The server temporarily holds the job in memory; it never publishes.
"""
PAGE_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MACIE C | Document Review</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#182936;background:#eef3f4}
*{box-sizing:border-box}body{margin:0}header{background:#123342;color:white;padding:22px 5vw;display:flex;align-items:center;justify-content:space-between;gap:16px}
.brand{font-weight:800;font-size:22px;letter-spacing:.4px}.brand span{font-weight:400;opacity:.75;font-size:13px;margin-left:12px}
main{max-width:1040px;margin:0 auto;padding:32px 22px 70px}.card{background:white;border:1px solid #d6e3e4;border-radius:16px;padding:28px;margin-bottom:22px;box-shadow:0 6px 22px #17434f0b}
h1{font-size:29px;margin:0 0 10px;color:#123342}h2{margin:0 0 13px;font-size:19px;color:#123342}
p{line-height:1.55}.muted{color:#546a74;font-size:14px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:18px}
label{display:block;margin:15px 0 7px;font-size:14px;font-weight:650;color:#273f4a}
input,textarea{font:inherit;border:1px solid #b6c9cf;border-radius:8px;width:100%;padding:12px;background:white;color:#162b33}
textarea{min-height:180px;resize:vertical;line-height:1.45}#goal{min-height:110px}input:focus,textarea:focus,button:focus{outline:3px solid #93c8cf;outline-offset:2px}
button{cursor:pointer;background:#136b76;border:0;border-radius:8px;color:white;font:inherit;font-weight:700;padding:13px 20px}
button:hover{background:#0d5560}button:disabled{opacity:.58;cursor:wait}.quiet{color:#fff;background:#496572;padding:8px 13px;font-size:13px}
.notice{background:#edf6f3;border-left:4px solid #4b988e;padding:14px 18px;margin:20px 0;border-radius:5px}
.warning{background:#fff5dd;border-left:4px solid #b07b16;padding:12px 16px;border-radius:4px}
#error{color:#9b2424;font-weight:700;white-space:pre-wrap}#message{font-weight:650;color:#164f58}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f6f7;border:1px solid #d9e4e5;border-radius:8px;padding:17px;font:14px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;max-height:650px;overflow:auto}
details{margin:15px 0;border:1px solid #d7e4e6;border-radius:8px;padding:13px}summary{cursor:pointer;font-weight:650}
#results{display:none}#results.visible{display:block}.actions{display:flex;flex-wrap:wrap;gap:9px;margin:18px 0}
.meta{display:flex;flex-wrap:wrap;gap:12px;font-size:14px;color:#3a5a64}
.badge{display:inline-block;background:#e2f1ed;padding:5px 9px;border-radius:6px;color:#115648;font-weight:650}
footer{text-align:center;font-size:12px;color:#687c81;margin:24px}
@media(max-width:720px){.columns{grid-template-columns:1fr}.card{padding:18px}header{padding:20px}.brand span{display:block;margin:5px 0 0}}
</style></head><body>
<header><div class="brand">MACIE C <span>Independent AI document review</span></div>
{% if email %}<button class="quiet" id="logout">Sign out</button>{% else %}
<div style="font-size:13px;opacity:.8">Authorized access only</div>{% endif %}</header>
<main>
{% if not email %}
<section class="card" style="max-width:500px;margin:24px auto">
<h1>Sign in to MACIE C</h1>
<p class="muted">Use the individual account credentials provided by the MACIE administrator. MACIE A private context is not part of this service.</p>
<form id="loginForm"><label for="email">Email</label><input id="email" type="email" required autocomplete="username">
<label for="password">Password</label><input id="password" type="password" required autocomplete="current-password">
<p id="error" role="alert"></p><button type="submit">Sign in securely</button></form>
<p class="muted">Your access must be activated by the administrator before you can sign in.</p>
</section>
{% else %}
<section class="card" id="providerPanel">
<h1>Step 1 — Connect your own AI key</h1>
<p>MACIE C uses <strong>your OpenRouter account</strong> for Claude and GPT reviews. Your provider charges apply to your own OpenRouter credits. This is separate from the MACIE C product subscription, which is not yet commercially available.</p>
<p class="muted">Create a dedicated <strong>standard API key</strong> in your OpenRouter account. Set an account/key spending limit and keep the key private. Do not use a management or administrative key. <a href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer noopener">Open OpenRouter key settings</a>.</p>
<form id="providerForm">
<label for="providerKey">Your OpenRouter API key (stored only in this browser sign-in session)</label>
<input id="providerKey" type="password" autocomplete="off" spellcheck="false"
placeholder="sk-or-v1-..." maxlength="400" required>
<p id="providerError" role="alert"></p>
<div class="actions">
<button id="connectKey" type="submit">Connect / replace my key</button>
<button id="disconnectKey" class="quiet" type="button">Disconnect my key</button>
</div>
<p id="providerStatus" role="status" class="muted">Checking your provider connection...</p>
</form>
<div class="notice">This controlled pilot encrypts the key in temporary server memory. You will connect it again after sign-out or server restart. The sellable product requires a secure, durable customer-owned key vault; MACIE C never asks its founder to supply your provider key.</div>
</section>
<section class="card">
<h1>Step 2 — Review an existing document</h1>
<div class="meta"><span>Signed in: <strong>{{ email }}</strong></span><span class="badge">Draft review only</span></div>
<p>Paste material below, or select a <strong>Word (.docx)</strong> or <strong>TXT</strong> file. Both AI models independently review it; MACIE then compares their findings and shows agreements and disagreements.</p>
<div class="notice">Your original is not altered or published. The server retains the job briefly in memory (about 30 minutes), and the content is sent to configured AI providers for review. Do not submit sensitive personal/customer data without permission and approved privacy controls.</div>
<form id="reviewForm">
<div class="columns"><div><label for="file">Optional file</label><input id="file" name="file" type="file" accept=".docx,.txt"><div class="muted">Maximum 2 MB; one file per review.</div>
<label for="document">Existing material</label><textarea id="document" name="document" maxlength="50000" placeholder="Paste an existing brochure, script, proposal, or other material here..."></textarea></div>
<div><label for="goal">Review instructions</label><textarea id="goal" name="goal" maxlength="2000">Identify unsupported statements and practical weaknesses, improve clarity and usefulness, preserve facts, explain the changes, and flag unresolved disagreements. Provide an improved ready-to-review version.</textarea>
<p class="muted">Examples: “Check claims in this Realtor brochure, then rewrite it”; “Critique this proposal for feasibility, costs and security.”</p>
<div class="warning"><strong>Human approval required:</strong> MACIE C never sends, publishes, or changes your source document. Verify factual claims before using revised marketing materials.</div>
</div></div>
<p id="error" role="alert"></p><p id="message" role="status"></p>
<button id="submit" type="submit">Run independent MACIE C review</button>
</form></section>
<section class="card" id="results" aria-live="polite"><h2>MACIE C review results</h2>
<div id="state" class="meta"></div><div class="actions">
<button type="button" id="txtDownload">Download review (.txt)</button>
<button type="button" id="jsonDownload">Download full record (.json)</button>
</div>
<h2>Consensus / enhanced material</h2><pre id="synthesis"></pre>
<h2>Unresolved disagreements</h2><pre id="divergences"></pre>
<details><summary>Claude — independent review</summary><pre id="claudeReview"></pre></details>
<details><summary>ChatGPT — independent review</summary><pre id="chatgptReview"></pre></details>
</section>
{% endif %}
</main><footer>ActionForge Labs · MACIE C · No automatic publication · Commercial signup not yet released · Controlled pilot access only</footer>
<script nonce="{{ nonce }}">
(function(){
"use strict";
const qs=id=>document.getElementById(id);
const csrf={{ csrf|tojson }};
const err=qs("error");
function error(msg){if(err)err.textContent=String(msg||"An error occurred.");}
async function api(url, opts){
 const r=await fetch(url,Object.assign({credentials:"same-origin",cache:"no-store"},opts||{}));
 let data;try{data=await r.json();}catch(e){throw Error("Unexpected server response.");}
 if(!r.ok)throw Error(data.error||("Request failed: "+r.status));
 return data;
}
const login=qs("loginForm");
if(login)login.addEventListener("submit",async e=>{
 e.preventDefault();error("");
 try{await api("/macie/c/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:qs("email").value,password:qs("password").value})});location.assign("/macie/c");}
 catch(ex){error(ex.message);}
});
const logout=qs("logout");
if(logout)logout.addEventListener("click",async()=>{
 try{await api("/macie/c/logout",{method:"POST",headers:{"X-CSRF-Token":csrf}});location.assign("/macie/c");}
 catch(ex){error(ex.message);}
});
const form=qs("reviewForm");if(!form)return;
const providerForm=qs("providerForm"), providerStatus=qs("providerStatus"),
      providerError=qs("providerError"), providerKey=qs("providerKey");
function providerMessage(connected){
 providerStatus.textContent=connected?
  "Connected: Your own OpenRouter key is ready for this session. You may now review documents.":
  "Not connected. Connect your own OpenRouter key before running a review.";
}
async function checkProvider(){
 try{const info=await api("/macie/c/provider");providerMessage(info.connected);}
 catch(ex){providerStatus.textContent="Provider status could not be checked.";}
}
checkProvider();
providerForm.addEventListener("submit",async e=>{
 e.preventDefault();providerError.textContent="";
 const key=providerKey.value;qs("connectKey").disabled=true;
 try{
  const response=await api("/macie/c/provider",{
   method:"POST",headers:{"X-CSRF-Token":csrf,"Content-Type":"application/json"},
   body:JSON.stringify({api_key:key})
  });
  providerMessage(response.connected);providerKey.value="";
 }catch(ex){providerError.textContent=ex.message;}
 finally{qs("connectKey").disabled=false;}
});
qs("disconnectKey").addEventListener("click",async()=>{
 providerError.textContent="";
 try{
  await api("/macie/c/provider",{method:"DELETE",headers:{"X-CSRF-Token":csrf}});
  providerKey.value="";providerMessage(false);
 }catch(ex){providerError.textContent=ex.message;}
});
let last=null;
const run=qs("submit"), msg=qs("message");
const status=qs("state"), synthesis=qs("synthesis"), divergences=qs("divergences");
const reviews={claude:qs("claudeReview"),chatgpt:qs("chatgptReview")};
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function show(result){
 last=result;qs("results").classList.add("visible");
 status.textContent="Status: "+result.status+" | Confidence: "+result.confidence+" | Models: "+result.models_succeeded.join(", ");
 synthesis.textContent=result.synthesized_review||result.raw_fallback||"No verified consensus. Check model responses and retry.";
 divergences.textContent=result.divergences&&result.divergences.length?JSON.stringify(result.divergences,null,2):"No disagreements reported.";
 for(const name of Object.keys(reviews)){
  const x=(result.model_outputs||[]).find(o=>o.model_id===name);
  reviews[name].textContent=x?((x.raw_review||x.error||"No response")+"\n\nModel: "+x.model_version):"No response";
 }
}
form.addEventListener("submit",async e=>{
 e.preventDefault();error("");msg.textContent="";run.disabled=true;last=null;qs("results").classList.remove("visible");
 const data=new FormData();data.set("document",qs("document").value);data.set("goal",qs("goal").value);
 if(qs("file").files.length)data.set("file",qs("file").files[0]);
 try{
  const job=await api("/macie/c/review",{method:"POST",headers:{"X-CSRF-Token":csrf},body:data});
  msg.textContent="Review submitted. Claude and ChatGPT are evaluating independently...";
  let done=false;
  for(let i=0;i<150;i++){
   await pause(1800);
   const resp=await api("/macie/c/review/"+encodeURIComponent(job.job_id));
   if(resp.status==="finished"){show(resp.result);msg.textContent="Review completed. Download the result if you wish to preserve it.";done=true;break;}
   if(resp.status==="failed")throw Error(resp.error||"Review failed.");
   if(i%5===0)msg.textContent="Review in progress; please keep this tab open.";
  }
  if(!done)throw Error("The review is taking longer than expected. Please retry after checking service status.");
 }catch(ex){error(ex.message);msg.textContent="";}
 finally{run.disabled=false;}
});
function download(filename,content,mime){
 const url=URL.createObjectURL(new Blob([content],{type:mime}));
 const a=document.createElement("a");a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
qs("jsonDownload").addEventListener("click",()=>{
 if(last)download("MACIE-C-review.json",JSON.stringify(last,null,2),"application/json");
});
qs("txtDownload").addEventListener("click",()=>{
 if(!last)return;
 const parts=["MACIE C DOCUMENT REVIEW","STATUS: "+last.status,"CONFIDENCE: "+last.confidence,"","ENHANCED MATERIAL / CONSENSUS",last.synthesized_review||last.raw_fallback||"","DISAGREEMENTS",JSON.stringify(last.divergences||[],null,2),"","CLAUDE",reviews.claude.textContent,"","CHATGPT",reviews.chatgpt.textContent];
 download("MACIE-C-review.txt",parts.join("\n"),"text/plain");
});
})();
</script>
</body></html>
"""
