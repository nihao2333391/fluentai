import type { TFunction } from 'i18next'

import type { MeshingSchemaTask } from '../../../shared/contracts'
import i18n from '../i18n'
import { localizedAnsysTerm } from '../i18n/ansysLabels'

const TASK_NAME_KEYS: Record<string, string> = {
  import_cad_and_part_management: 'importCadAndPartManagement',
  enclose_fluid_regions_fault: 'encloseFluidRegionsFault',
  compute_size_fields: 'computeSizeFields',
  identify_construction_surfaces: 'identifyConstructionSurfaces',
  update_region_settings: 'updateRegionSettings',
  create_volume_mesh: 'createVolumeMesh',
  create_porous_regions: 'createPorousRegions',
  generate_prism_layers: 'generatePrismLayers',
  generate_volume_mesh: 'generateVolumeMesh',
  setup_size_controls: 'setupSizeControls',
  remesh_surface: 'remeshSurface',
  create_local_refinement_regions: 'createLocalRefinementRegions',
  compute_regions: 'computeRegions',
  close_leakage: 'closeLeakage',
  add_boundary_layer_ftm: 'addBoundaryLayerFtm',
  identify_regions: 'identifyRegions',
  describe_geometry_and_flow: 'describeGeometryAndFlow',
  create_external_flow_boundaries: 'createExternalFlowBoundaries',
  choose_mesh_control_options: 'chooseMeshControlOptions',
  define_leakage_threshold: 'defineLeakageThreshold',
  create_zero_thickness_geometry: 'createZeroThicknessGeometry',
  update_boundaries_ftm: 'updateBoundariesFtm',
  extract_edge_features: 'extractEdgeFeatures',
  mesh_controls_table: 'meshControlsTable',
  generate_surface_mesh: 'generateSurfaceMesh',
  create_regions: 'createRegions',
  update_regions: 'updateRegions',
  describe_geometry: 'describeGeometry',
  enclose_fluid_regions: 'encloseFluidRegions',
  update_boundaries: 'updateBoundaries',
  import_geometry: 'importGeometry',
  create_surface_mesh: 'createSurfaceMesh',
  apply_share_topology: 'applyShareTopology',
  add_boundary_layer: 'addBoundaryLayer',
  add_local_sizing: 'addLocalSizing',
}

const TASK_TYPE_KEYS: Record<string, string> = {
  Simple: 'simple',
  Compound: 'compound',
  Conditional: 'conditional',
  'Compound Child': 'compoundChild',
}

export const localizedMeshingTaskName = (t: TFunction, task: MeshingSchemaTask): string => {
  const key = TASK_NAME_KEYS[task.python_name]
  if (i18n.language.toLowerCase().startsWith('zh')) {
    return localizedAnsysTerm(
      task.display_name,
      key ? t(`meshing.taskNames.${key}`) : task.display_name,
    )
  }
  return task.display_name
}

export const localizedMeshingTaskType = (t: TFunction, taskType: string | null): string => {
  const key = taskType ? TASK_TYPE_KEYS[taskType] : undefined
  return key ? t(`meshing.taskTypes.${key}`) : (taskType ?? '')
}
