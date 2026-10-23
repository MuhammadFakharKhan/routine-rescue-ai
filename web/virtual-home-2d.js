import { deriveVirtualHomeModel } from './virtual-home-state.js';

const byId = (id) => document.getElementById(id);

/** Derive presentational facts from observed state and verification evidence only. */
export function describeVirtualHome2D(state, receipt = {}, recoveryProof = null) {
  const model = deriveVirtualHomeModel(state, receipt);
  const lightLabel = !model.lightKnown ? model.uncertain ? 'UNVERIFIED' : 'UNKNOWN' : model.lightOn ? 'ON' : 'OFF';
  const doorLabel = !model.doorKnown ? model.uncertain ? 'UNVERIFIED' : 'UNKNOWN' : model.doorLocked ? 'LOCKED' : 'UNLOCKED';
  const positionLabel = model.doorOpenKnown ? model.doorOpen ? 'OPEN (OBSERVED)' : 'CLOSED (OBSERVED)' : 'POSITION NOT MODELED';
  const alarmLabel = model.alarmTime ? `ALARM ${model.alarmTime}` : 'NO ALARM SET';
  let notice = `Observed state synchronized. Latest workflow outcome: ${model.outcome}.`;
  let noticeKind = '';
  if (model.mismatch) {
    notice = `Verification mismatch: command reported success, but the light remains ON. Expected ${model.mismatchExpected}; observed ${model.mismatchObserved}.`;
    noticeKind = 'is-warning';
  } else if (model.uncertain) {
    notice = 'Observation is unavailable or unverified. This illustration does not infer a successful device change.';
    noticeKind = 'is-unknown';
  } else if (recoveryProof?.verified) {
    notice = 'Recovery verified by the local simulator after observed-state readback. Unrelated devices remain unchanged.';
    noticeKind = 'is-recovered';
  }
  return { model, lightLabel, doorLabel, positionLabel, alarmLabel, notice, noticeKind };
}

/** Update the inline SVG room from SQLite-backed observed state. */
export function updateVirtualHome2D(state, receipt = {}, recoveryProof = null) {
  const view = describeVirtualHome2D(state, receipt, recoveryProof);
  const { model } = view;
  const scene = byId('virtual-home-2d-scene');
  scene.className = [
    'virtual-home-2d-scene',
    model.lightOn ? 'is-light-on' : 'is-light-off',
    !model.lightKnown ? 'is-light-unknown' : '',
    model.doorLocked ? 'is-door-locked' : 'is-door-unlocked',
    model.doorOpen ? 'is-door-open' : 'is-door-closed',
    model.mismatch ? 'has-mismatch' : '',
  ].filter(Boolean).join(' ');
  scene.setAttribute('aria-label', `Simulated observed room: living light ${view.lightLabel}; front door ${view.doorLabel}, ${view.positionLabel.toLowerCase()}; ${view.alarmLabel.toLowerCase()}.`);

  byId('virtual-light-status').textContent = view.lightLabel;
  byId('virtual-light-detail').textContent = model.mismatch ? `Expected ${model.mismatchExpected}; observed ${model.mismatchObserved}` : 'Observed from local simulator';
  byId('virtual-door-status').textContent = view.doorLabel;
  byId('virtual-door-detail').textContent = model.doorOpenKnown ? `Physical position: ${view.positionLabel.toLowerCase()}` : 'Physical position not modeled — never inferred from unlock';
  byId('virtual-alarm-status').textContent = view.alarmLabel;
  byId('virtual-alarm-detail').textContent = 'Simulated scheduled alarm; not a physical notification';
  byId('virtual-home-verification').textContent = model.outcome === 'OBSERVED' ? 'Observed state' : model.outcome;
  byId('virtual-home-verification').className = `chip ${model.mismatch || model.outcome === 'DEGRADED' ? 'bad' : model.uncertain ? 'unknown' : model.outcome === 'VERIFIED' || model.outcome === 'RECOVERED' ? 'good' : ''}`.trim();
  const notice = byId('virtual-home-notice');
  notice.className = `virtual-home-notice ${view.noticeKind}`.trim();
  notice.textContent = view.notice;
  byId('scene-light-value').textContent = view.lightLabel;
  byId('scene-door-lock-text').textContent = view.doorLabel;
  byId('scene-door-position-text').textContent = view.positionLabel;
  byId('scene-alarm-text').textContent = model.alarmTime || 'NO ALARM';
  byId('scene-alarm-indicator').textContent = model.alarmTime ? 'ALARM SET' : 'NO ALARM SET';
  return view;
}
