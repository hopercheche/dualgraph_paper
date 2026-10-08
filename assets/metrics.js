(() => {
  'use strict';
  const names = {status:'Requirement state', consequence:'Rule consequence', revision:'Error and correction', review:'Faculty review'};
  const gold = {status:'MET', consequence:'CAP_CPLUS', revision:'NO_ERROR', review:'0'};
  const controls = Object.fromEntries(Object.keys(gold).map(k => [k, document.getElementById('egj-'+k)]));
  const result = document.getElementById('egj-decision-result');
  if (!result) return;
  function decision() {
    const mismatches = [];
    for (const k of Object.keys(gold)) {
      const pass = controls[k].value === gold[k];
      const cell = document.querySelector('[data-match="'+k+'"]');
      cell.textContent = pass ? 'Match' : 'Mismatch';
      cell.className = pass ? 'metric-match-pass' : 'metric-match-fail';
      if (!pass) mismatches.push(names[k]);
    }
    const pass = mismatches.length === 0;
    result.classList.toggle('fail', !pass);
    result.dataset.score = pass ? '1' : '0';
    const title = document.createElement('b');
    title.textContent = 'Assessment exact match = '+(pass ? '1' : '0');
    const why = document.createElement('span');
    why.textContent = pass ? 'All four prespecified fields match; this record contributes to the assessment numerator.' :
      controls.status.value === 'FAIL' ? 'No valid assessment output: failure remains in the denominator.' :
      mismatches.join(', ')+' differs. Even if other fields are correct, the complete decision is scored 0.';
    result.replaceChildren(title, why);
  }
  for (const el of Object.values(controls)) el.addEventListener('change', () => {
    document.querySelectorAll('[data-decision-preset]').forEach(b => b.classList.remove('active'));
    decision();
  });
  const presets = {
    correct:gold,
    'missing-cap':{...gold, consequence:'NONE'},
    'invent-error':{...gold, revision:'UNRESOLVED'},
    'unneeded-review':{...gold, review:'1'},
    failed:{...gold, status:'FAIL'}
  };
  document.querySelectorAll('[data-decision-preset]').forEach(button => button.addEventListener('click', () => {
    const chosen = presets[button.dataset.decisionPreset];
    for (const k of Object.keys(gold)) controls[k].value = chosen[k];
    document.querySelectorAll('[data-decision-preset]').forEach(b => b.classList.toggle('active', b === button));
    decision();
  }));
  function role() {
    const boxes = [...document.querySelectorAll('[data-role-check]')];
    const pass = boxes.every(b => b.checked);
    const target = document.getElementById('egj-role-result');
    target.classList.toggle('fail', !pass);
    target.dataset.score = pass ? '1' : '0';
    const title = document.createElement('b');
    title.textContent = 'Role compliance = '+(pass ? '1' : '0');
    const why = document.createElement('span');
    why.textContent = pass ? 'Valid reply; R1, R2 and R3 all pass.' :
      !boxes[0].checked ? 'No valid reply; scored 0.' :
      boxes.filter(b => !b.checked).map(b => b.dataset.roleCheck).join(', ')+' failed; checks are not averaged, so the reply is scored 0.';
    target.replaceChildren(title, why);
  }
  document.querySelectorAll('[data-role-check]').forEach(b => b.addEventListener('change', role));
  decision(); role();
})();
