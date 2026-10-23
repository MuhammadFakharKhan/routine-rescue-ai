/**
 * Convert the backend's observed virtual-device state into display facts.
 * This module never uses action acknowledgement as a source of device truth.
 */
export function deriveVirtualHomeModel(state, verificationInfo = {}) {
  const livingPower = state?.living_light?.power;
  const doorLocked = state?.front_door?.locked;
  const doorOpen = state?.front_door?.open === true;
  const alarmTime = state?.alarm?.time ?? null;
  const violations = Array.isArray(verificationInfo?.violations) ? verificationInfo.violations : [];
  const lightViolation = violations.find((item) => item.target === 'living_light' && item.field === 'power');
  const outcome = verificationInfo?.outcome || 'OBSERVED';
  const uncertain = outcome === 'UNVERIFIED' || livingPower === undefined || doorLocked === undefined || state?.alarm === undefined;
  const mismatch = Boolean(lightViolation && livingPower === 'on' && lightViolation.expected === 'off');

  return {
    lightOn: livingPower === 'on',
    lightKnown: livingPower === 'on' || livingPower === 'off',
    deskLightOn: state?.desk_light?.power === 'on',
    ambientLightOn: state?.ambient_light?.power === 'on',
    doorLocked: doorLocked === true,
    doorKnown: typeof doorLocked === 'boolean',
    doorOpen,
    doorOpenKnown: typeof state?.front_door?.open === 'boolean',
    alarmTime: typeof alarmTime === 'string' ? alarmTime : null,
    mismatch,
    mismatchExpected: mismatch ? String(lightViolation.expected).toUpperCase() : null,
    mismatchObserved: mismatch ? String(livingPower).toUpperCase() : null,
    uncertain,
    outcome,
  };
}
