const el = id => document.getElementById(id);
let receipt;
el('review').addEventListener('click', async () => {
  el('review').disabled = true;
  el('result').hidden = true;
  el('status').textContent = 'Requesting independent reviews…';
  try {
    const response = await fetch('/macie-c/review', {method:'POST',
      headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},
      body:JSON.stringify({document:el('document').value})});
    receipt = await response.json();
    if (!response.ok) throw new Error(receipt.error || 'Review request failed.');
    el('status').textContent = receipt.status;
    el('receipt').textContent = `Review ${receipt.review_id} · ${receipt.created_at}`;
    el('revision').textContent = receipt.result?.improved_document || receipt.blocker;
    el('changes').textContent = receipt.result ? JSON.stringify({weaknesses:receipt.result.weaknesses,changes:receipt.result.change_log,agreements:receipt.result.agreements,unresolved_disagreements:receipt.result.unresolved_disagreements},null,2) : 'No completed revision is available.';
    el('evidence').textContent = JSON.stringify(receipt,null,2);
    el('approve').disabled = !receipt.result;
    el('approval').textContent = 'Awaiting your review. Approval here records your decision in the downloaded copy only.';
    el('result').hidden = false;
  } catch(error) { el('status').textContent = error.message; }
  finally { el('review').disabled = false; }
});
el('approve').addEventListener('click', () => {
  receipt.approved = true;
  receipt.approved_at = new Date().toISOString();
  el('approval').textContent = 'This copy is marked approved. Download it to retain your decision. Nothing has been published or executed.';
  el('evidence').textContent = JSON.stringify(receipt,null,2);
});
el('download').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = `macie-c-${receipt.review_id}.json`; a.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
});
