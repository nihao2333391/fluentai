import type { TFunction } from 'i18next'

const LABEL_KEYS: Record<string, string> = {
  'solver.time': 'solverTime',
  'solver.type': 'solverType',
  'solver.velocity_formulation': 'velocityFormulation',
  'energy.enabled': 'energyEquation',
  'viscous.model': 'viscousModel',
  'viscous.k_omega_model': 'kOmegaModel',
  'viscous.low_re_correction': 'lowReCorrection',
  'viscous.curvature_correction': 'curvatureCorrection',
  'viscous.corner_flow_correction': 'cornerFlowCorrection',
  'methods.flow_scheme': 'flowScheme',
  'methods.gradient_scheme': 'gradientScheme',
  'controls.flow_equations': 'flowEquations',
  'initialization.type': 'initializationType',
  'initialization.reference_frame': 'initializationReferenceFrame',
  'run_calculation.iterations': 'runIterations',
  'run_calculation.reporting_interval': 'reportingInterval',
  'monitor.residual.criterion_type': 'criterionType',
  'monitor.residual.save_count': 'saveCount',
  'monitor.residual.display_count': 'displayCount',
  'monitor.residual.normalize': 'normalizeResiduals',
  'monitor.residual.print': 'printResiduals',
  'monitor.residual.plot': 'plotResiduals',
  'reference.area': 'referenceArea',
  'reference.density': 'referenceDensity',
  'reference.length': 'referenceLength',
  'reference.velocity': 'referenceVelocity',
  'reference.viscosity': 'referenceViscosity',
}

const EQUATION_KEYS: Record<string, string> = {
  continuity: 'continuity',
  'x-velocity': 'xVelocity',
  'y-velocity': 'yVelocity',
  'z-velocity': 'zVelocity',
  k: 'k',
  omega: 'omega',
}

const BOUNDARY_FIELD_KEYS: Record<string, string> = {
  velocity_magnitude: 'velocityMagnitude',
  gauge_pressure: 'gaugePressure',
  turbulent_intensity: 'turbulentIntensity',
  turbulent_viscosity_ratio: 'turbulentViscosityRatio',
  backflow_turbulent_intensity: 'backflowTurbulentIntensity',
  backflow_turbulent_viscosity_ratio: 'backflowTurbulentViscosityRatio',
  roughness_height: 'roughnessHeight',
  roughness_constant: 'roughnessConstant',
}

const OPTION_KEYS: Record<string, Record<string, string>> = {
  'solver.time': {
    steady: 'steady',
    'unsteady-1st-order': 'unsteady1stOrder',
    'unsteady-2nd-order': 'unsteady2ndOrder',
    'unsteady-2nd-order-bounded': 'unsteady2ndOrderBounded',
  },
  'solver.type': {
    'pressure-based': 'pressureBased',
    'density-based-implicit': 'densityBasedImplicit',
    'density-based-explicit': 'densityBasedExplicit',
  },
  'solver.velocity_formulation': {
    absolute: 'absolute',
    relative: 'relative',
  },
  'viscous.model': {
    inviscid: 'inviscid',
    laminar: 'laminar',
    'k-epsilon': 'kEpsilon',
    'k-omega': 'kOmega',
    'mixing-length': 'mixingLength',
    'spalart-allmaras': 'spalartAllmaras',
    'k-kl-w': 'kKlW',
    'transition-sst': 'transitionSst',
    'reynolds-stress': 'reynoldsStress',
    'scale-adaptive-simulation': 'scaleAdaptiveSimulation',
    'detached-eddy-simulation': 'detachedEddySimulation',
    'large-eddy-simulation': 'largeEddySimulation',
  },
  'viscous.k_omega_model': {
    standard: 'standard',
    geko: 'geko',
    bsl: 'bsl',
    sst: 'sst',
    'wj-bsl-earsm': 'wjBslEarsm',
  },
  'methods.flow_scheme': {
    SIMPLE: 'simple',
    SIMPLEC: 'simplec',
    PISO: 'piso',
    Coupled: 'coupled',
  },
  'methods.gradient_scheme': {
    'green-gauss-node-based': 'greenGaussNodeBased',
    'green-gauss-cell-based': 'greenGaussCellBased',
    'least-square-cell-based': 'leastSquareCellBased',
  },
  'initialization.type': {
    standard: 'standardInitialization',
    hybrid: 'hybridInitialization',
  },
  'initialization.reference_frame': {
    relative: 'relative',
    absolute: 'absolute',
  },
  'monitor.residual.criterion_type': {
    absolute: 'absolute',
    none: 'none',
  },
}

export const localizedSettingLabel = (
  t: TFunction,
  settingId: string,
  fallback: string,
): string => {
  const labelKey = LABEL_KEYS[settingId]
  if (labelKey) return t(`settingLabels.${labelKey}`)

  if (settingId.startsWith('residual.')) {
    const equation = settingId.slice('residual.'.length)
    return `${t('settingLabels.residualCriterion')} · ${t(
      `settingLabels.equations.${EQUATION_KEYS[equation] ?? 'continuity'}`,
    )}`
  }
  if (settingId.startsWith('monitor.residual.monitor.')) {
    const equation = settingId.slice('monitor.residual.monitor.'.length)
    return `${t('settingLabels.monitorResidual')} · ${t(
      `settingLabels.equations.${EQUATION_KEYS[equation] ?? 'continuity'}`,
    )}`
  }
  if (settingId.startsWith('material.fluid.')) {
    const [, , material, property] = settingId.split('.')
    const propertyLabel =
      property === 'density'
        ? t('settingLabels.materialDensity')
        : t('settingLabels.materialViscosity')
    return `${material} · ${propertyLabel}`
  }
  if (settingId.startsWith('boundary.')) {
    const [, , zone, field] = settingId.split('.')
    const fieldKey = BOUNDARY_FIELD_KEYS[field]
    if (fieldKey) return `${zone} · ${t(`settingLabels.boundaryFields.${fieldKey}`)}`
  }
  return fallback
}

export const localizedSettingOption = (t: TFunction, settingId: string, value: string): string => {
  const optionKey = OPTION_KEYS[settingId]?.[value]
  return optionKey ? t(`settingLabels.options.${optionKey}`) : value
}
