"""Self-service commercial MACIE C browser interface (NOT FOR SALE YET).

The entire commercial blueprint is disabled until tested DB, email sender,
merchant entitlement, privacy/cost controls and support arrangements exist.
"""
HTML=r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MACIE C — Your Account</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f1f5f4;color:#172f39}
*{box-sizing:border-box}body{margin:0}header{background:#163747;color:#fff;padding:22px max(20px,calc((100vw - 1000px)/2));}
main{max-width:1000px;margin:30px auto;padding:0 18px 40px}
section{background:#fff;padding:25px;border:1px solid #d3e0e2;border-radius:12px;margin-bottom:20px}
h1{font-size:26px;margin:0}h2{font-size:20px;color:#154552;margin-top:0}h3{font-size:16px;margin:0}
p{line-height:1.5}label{display:block;font-weight:600;margin:13px 0 5px}
input,textarea{display:block;width:100%;max-width:650px;border:1px solid #a9bcc2;border-radius:7px;font:inherit;padding:10px}
textarea{min-height:150px}button{font:inherit;font-weight:650;padding:11px 16px;margin:9px 8px 0 0;background:#116d78;color:#fff;border:0;border-radius:7px;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}.subtle{font-size:13px;color:#4c6670}.alert{background:#fff0d7;padding:14px;border-left:4px solid #bd800b;border-radius:4px}
.success{color:#17604b}.error{color:#a32b2b;white-space:pre-wrap}
.hide{display:none!important}.row{display:grid;grid-template-columns:1fr 1fr;gap:24px}
pre{background:#ecf3f2;padding:16px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:550px;overflow:auto}
@media(max-width:700px){.row{grid-template-columns:1fr}}
</style></head><body><header><h1>MACIE C · Customer Document Review</h1><div class="subtle" style="color:#d8e5e8">Independent AI critiques, reconciled suggestions, buyer-owned AI provider key</div></header>
<main>
<section class="alert"><strong>Commercial release is not open.</strong> This registration flow is under controlled security testing. A purchase does not occur until a separate verified checkout is available. Each buyer owns and pays for their own OpenRouter AI API key. No customer files are automatically published.</section>
<section id="notice" aria-live="polite" class="hide"><p id="noticeText"></p></section>
<section id="guest" {% if user_id %}class="hide"{% endif %}>
<div class="row"><div><h2>Create your account</h2>
<form id="signup"><label>Email<input name="email" type="email" required autocomplete="email"></label>
<label>Company/organization<input name="company" maxlength="160" required></label>
<label>Password (14+ characters)<input name="password" type="password" minlength="14" required autocomplete="new-password"></label>
<label><input name="accept_terms" type="checkbox" required style="width:auto;display:inline"> I agree to the <a href="{{ terms_url }}" target="_blank" rel="noreferrer noopener">MACIE C Terms</a> and <a href="{{ privacy_url }}" target="_blank" rel="noreferrer noopener">Privacy Policy</a>.</label>
<button type="submit">Create account and email verification link</button></form>
<form id="resend"><label>Resend verification link to email<input name="email" type="email" required></label>
<button type="submit">Resend</button></form>
</div><div><h2>Sign in</h2><form id="login">
<label>Email<input name="email" type="email" required autocomplete="username"></label>
<label>Password<input name="password" type="password" required autocomplete="current-password"></label>
<button type="submit">Sign in</button></form>
<h3>Forgot password?</h3><form id="forgot"><label>Email<input type="email" name="email" required></label>
<button type="submit">Send a reset link</button></form>
</div></div></section>
<section id="resetPanel" class="hide"><h2>Reset your password</h2>
<form id="resetForm"><label>Choose your new password (14+ characters)
<input id="newPassword" type="password" minlength="14" required autocomplete="new-password"></label>
<button type="submit">Save new password</button></form></section>
<section id="account" {% if not user_id %}class="hide"{% endif %}>
<div class="row"><div><h2>Your account</h2><p id="accountInfo">Loading...</p>
<p><strong>MACIE C subscription:</strong> {{ plan_display }}. Your own OpenRouter model usage is billed separately by OpenRouter. Charges and cancellation details are in the <a href="{{ terms_url }}" target="_blank" rel="noreferrer noopener">Terms</a>.</p>
<button id="logout" type="button">Sign out</button><button id="checkout" type="button">Choose and pay for subscription</button><button id="billing" type="button">Manage billing and cancel</button>
</div><div><h2>Connect your own model key</h2>
<p>Open an OpenRouter account, create a standard API key, and set your own spending limit. You pay OpenRouter directly for model usage. Claude and GPT use this one key, never the founder's credentials.</p>
<p><a href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer noopener">OpenRouter key settings</a></p>
<form id="provider"><label>OpenRouter completion API key<input id="apiKey" type="password" name="api_key" placeholder="sk-or-v1-..." required autocomplete="off"></label>
<button type="submit">Connect or replace my key</button><button id="disconnect" type="button">Delete my key</button></form>
<p id="providerState" class="subtle"></p></div></div>
</section>
<section id="review" {% if not user_id %}class="hide"{% endif %}>
<h2>Review existing content</h2>
<form id="reviewForm"><label>Paste your existing document<textarea name="document" maxlength="50000" required placeholder="Paste a previously drafted brochure, letter, proposal or procedure."></textarea></label>
<label>Review objective<textarea name="goal" maxlength="2000" required>Improve clarity, accuracy, usefulness and trustworthiness. Clearly identify unsupported claims and disagreements. Produce a revised draft with reasoning.</textarea></label>
<button type="submit">Run my independent MACIE C review</button></form><p id="reviewStatus"></p>
</section>
<section id="reviewOutput" class="hide"><h2>Review and recommendations</h2>
<h3>Consensus or NON-CONSENSUS</h3><pre id="synthesis"></pre><h3>Disagreements</h3><pre id="disagreements"></pre>
<h3>Claude independent review</h3><pre id="claude"></pre>
<h3>GPT independent review</h3><pre id="gpt"></pre>
<button type="button" id="download">Download complete review JSON</button>
</section>
<footer style="text-align:center;margin:30px;font-size:13px">Need help? <a href="mailto:{{ support_email }}">Customer support</a> · <a href="{{ privacy_url }}" target="_blank" rel="noreferrer noopener">Privacy</a></footer></main><script nonce="{{ nonce }}">
(()=>{"use strict";
const $=id=>document.getElementById(id);
let csrf={{ csrf|tojson }},last=null;
function msg(text,error=false){$("notice").classList.remove("hide");$("noticeText").className=error?"error":"success";$("noticeText").textContent=text;}
async function request(path,method="GET",data=null){
 const opts={method,cache:"no-store",credentials:"same-origin",headers:{}};
 if(data!==null){opts.headers["Content-Type"]="application/json";opts.body=JSON.stringify(data);}
 if(method!=="GET"&&csrf)opts.headers["X-CSRF-Token"]=csrf;
 const res=await fetch("/macie/c/commercial"+path,opts);let body={};
 try{body=await res.json();}catch(e){throw new Error("Server response could not be read.");}
 if(!res.ok)throw new Error(body.error||"Request rejected: "+res.status);
 return body;
}
function payload(form){return Object.fromEntries(new FormData(form).entries());}
function bind(name,path,extra={}){
 $(name).addEventListener("submit",async e=>{
  e.preventDefault();const f=e.currentTarget;const b=f.querySelector("button[type=submit]");b.disabled=true;
  try{let data=payload(f);Object.assign(data,extra);
   if(name==="signup")data.accept_terms=f.elements.accept_terms.checked;
   const result=await request(path,"POST",data);
   if(name==="login"){csrf=result.csrf;location.reload();return;}
   msg(result.message||"Action completed. Check your email if applicable.");f.reset();
  }catch(err){msg(err.message,true);}finally{b.disabled=false;}
 });
}
for(const [form,url,opts] of [
 ["signup","/signup",{}],["resend","/resend-verification",{}],
 ["login","/login",{}],["forgot","/request-reset",{}],
]){if($(form))bind(form,url,opts);}
const account=$("account");
if(account&&!account.classList.contains("hide")){
 const refresh=async()=>{const state=await request("/status");
  $("accountInfo").textContent=state.email+" · Subscription: "+state.subscription?.status+
    " · Reviews: "+state.subscription?.reviews_consumed+"/"+state.subscription?.review_limit;
  $("providerState").textContent=state.provider_connected?"Your OpenRouter key is connected.":"No AI key connected yet.";
 };refresh().catch(e=>msg(e.message,true));
 $("logout").addEventListener("click",async()=>{try{await request("/logout","POST",{});location.reload();}catch(e){msg(e.message,true);}});
 $("checkout").addEventListener("click",async()=>{
  try{const r=await request("/checkout","POST",{});if(r.checkout_url)location.assign(r.checkout_url);}
  catch(e){msg(e.message,true);}
 });
 $("billing").addEventListener("click",async()=>{
  try{const r=await request("/billing","POST",{});if(r.billing_portal_url)location.assign(r.billing_portal_url);}
  catch(e){msg(e.message,true);}
 });
 $("provider").addEventListener("submit",async e=>{
  e.preventDefault();
  try{await request("/provider","POST",{api_key:$("apiKey").value});
   $("apiKey").value="";msg("Key verified and connected to your own account.");refresh();
  }catch(err){msg(err.message,true);}
 });
 $("disconnect").addEventListener("click",async()=>{
  try{await request("/provider","DELETE",{});$("apiKey").value="";refresh();msg("Key deleted.");}
  catch(e){msg(e.message,true);}
 });
 $("reviewForm").addEventListener("submit",async e=>{
  e.preventDefault();let b=e.currentTarget.querySelector("button");b.disabled=true;last=null;$("reviewOutput").classList.add("hide");
  try{const job=await request("/review","POST",payload(e.currentTarget));
   $("reviewStatus").textContent="Independent reviews in progress...";
   for(let i=0;i<150;i++){
    await new Promise(done=>setTimeout(done,1800));
    const state=await request("/review/"+encodeURIComponent(job.job_id));
    if(state.status==="finished"){
      last=state.result;const x=last;
      $("synthesis").textContent=x.synthesized_review||x.raw_fallback||"NON-CONSENSUS — review provider responses.";
      $("disagreements").textContent=JSON.stringify(x.divergences||[],null,2);
      for(const [model,id] of [["claude","claude"],["chatgpt","gpt"]]){
       let row=(x.model_outputs||[]).find(r=>r.model_id===model);
       $(id).textContent=row?(row.raw_review||row.error||"No valid model response"):"No response";
      }
      $("reviewOutput").classList.remove("hide");
      $("reviewStatus").textContent="Completed: "+x.status;
      b.disabled=false;return;
    }
    if(state.status==="failed")throw new Error("Review failed. Your OpenRouter account or plan may require attention.");
   }
   throw new Error("Review is taking longer than expected.");
  }catch(err){msg(err.message,true);}finally{b.disabled=false;}
 });
 $("download").addEventListener("click",()=>{
  if(!last)return;const url=URL.createObjectURL(new Blob([JSON.stringify(last,null,2)],{type:"application/json"}));
  const a=document.createElement("a");a.href=url;a.download="MACIE-C-customer-review.json";a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
}
const query=new URLSearchParams(location.hash.replace(/^#/,""));
const verify=query.get("verify"),reset=query.get("reset");
if(verify){history.replaceState(null,"",location.pathname);
 request("/verify-email","POST",{token:verify})
 .then(x=>msg(x.message||"Email verified. Sign in."))
 .catch(e=>msg(e.message,true));}
if(reset){history.replaceState(null,"",location.pathname);
 $("resetPanel").classList.remove("hide");$("guest").classList.add("hide");
 $("resetForm").addEventListener("submit",async e=>{
  e.preventDefault();
  try{await request("/reset-password","POST",{token:reset,new_password:$("newPassword").value});
   $("newPassword").value="";$("resetPanel").classList.add("hide");
   $("guest").classList.remove("hide");
   msg("Password changed. Sign in with your new password.");
  }catch(err){msg(err.message,true);}
 });
}
})();
</script></body></html>"""
