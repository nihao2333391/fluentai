# Fluent Meshing Workflow Inventory - 2025 R2

- Status: inventory complete; Watertight and Fault-tolerant editing/apply implemented
- Reference: `D:\Fluent AI\wql.meshed.wbpj`
- Native workflow: `wql.meshed_files\dp0\FFF\Fluent\FFF_workflow_files\FFF.wft`
- Workbench version: 2025 R2
- Workflow type: Watertight Geometry
- Workflow schema version: 25.2

## Confirmed Public APIs

PyFluent Meshing exposes:

- `session.watertight()` for a new Watertight Geometry workflow
- `session.fault_tolerant()` for a new Fault-tolerant Meshing workflow
- `session.load_workflow(path)` for saved `.wft` files
- `workflow.task_names()`, `workflow.tasks()`, `workflow.task(name)`
- task objects with command arguments, state, child tasks, allowed values and edit paths

## Observed Watertight Top-Level Tasks

The reference `.wft` contains:

1. Import Geometry
2. Add Local Sizing
3. Generate the Surface Mesh
4. Describe Geometry
5. Apply Share Topology
6. Enclose Fluid Regions (Capping)
7. Update Boundaries
8. Create Regions
9. Update Regions
10. Add Boundary Layers
11. Generate the Volume Mesh

The factory-created Watertight workflow also exposes the task accessors:

- `import_geometry`
- `add_local_sizing`
- `create_surface_mesh`
- `describe_geometry`
- `apply_share_topology`
- `enclose_fluid_regions`
- `update_boundaries`
- `create_regions`
- `update_regions`
- `add_boundary_layer`
- `create_volume_mesh`

`Describe Geometry` is a conditional task. Share Topology, Capping, and Create Regions are conditionally active.

## Confirmed Reference Arguments

### Import Geometry

```json
{
  "FileName": "FFF.dsco",
  "LengthUnit": "m",
  "NumParts": "1"
}
```

### Add Local Sizing

Parent argument:

```json
{ "AddChild": "yes" }
```

Child controls include:

- BOI control name
- scope to faces
- face label/zone list
- size assignment method
- min/max size
- growth rate
- curvature normal angle
- cells per gap
- number of layers
- smallest height
- bias factor
- growth method
- ignore orientation

Reference children:

- `wall-big`
- `wall-samll` (name preserved exactly as stored in the project)

### Generate the Surface Mesh

```json
{
  "CFDSurfaceMeshControls": {
    "MaxSize": 0.002,
    "MinSize": 0.0005
  },
  "ExecuteShareTopology": "No",
  "OriginalZones": ["outlet", "inlet-hot", "inlet-cold", "wall-big", "wall-small"]
}
```

### Describe Geometry

```json
{
  "FluidRegions": ["wenqiuli"],
  "NonConformal": "No",
  "OldZoneList": ["outlet", "inlet-hot", "inlet-cold"],
  "SetupType": "The geometry consists of only fluid regions with no voids"
}
```

### Update Boundaries

```json
{
  "BoundaryLabelList": ["inlet-cold"],
  "BoundaryLabelTypeList": ["pressure-outlet"],
  "OldBoundaryLabelList": ["inlet-cold"],
  "OldBoundaryLabelTypeList": ["velocity-inlet"],
  "OldLabelZoneList": ["inlet-cold"]
}
```

### Add Boundary Layers

Reference child `smooth-transition_1` includes:

- BL control name
- region scope
- wall zone scope
- continuous prism preference

### Generate the Volume Mesh

```json
{
  "MeshSolidRegions": false,
  "VolumeFill": "poly-hexcore",
  "VolumeFillControls": {
    "HexMaxSize": 0.0032
  },
  "VolumeMeshPreferences": {
    "CheckSelfProximity": "yes",
    "ShowVolumeMeshPreferences": "true"
  }
}
```

## Known PyFluent Limitation

`session.load_workflow("FFF.wft")` in PyFluent 0.42.1 fails while initializing task accessors with:

```text
TypeError: attribute name must be string, not 'NoneType'
```

Both legacy and non-legacy flags fall back to the same legacy implementation for Fluent 25.2.

The implementation will therefore use:

1. `session.watertight()` / `session.fault_tolerant()` to create canonical workflow objects.
2. Live workflow/task argument introspection for option metadata.
3. `.wft` reference values and JSON structure for baseline snapshots and verification.

## Implementation Direction

- Add a separate Meshing Automation domain from Solver Automation.
- Version the schema as `fluent-meshing-25.2-watertight` and `fluent-meshing-25.2-fault-tolerant`.
- Store task/option edit paths exactly as exposed by the official API.
- Preserve conditional tasks and collapsed advanced groups.
- Apply presets by writing task arguments and reading them back.
- Stop before generation commands.
- Validate every required boundary, face zone, region and local-sizing scope name against the target model.
- Never use fuzzy or silent name substitution.

## Generated Schema Files

- `docs/meshing/fluent-meshing-25.2-watertight.schema.json`
- `docs/meshing/fluent-meshing-25.2-fault-tolerant.schema.json`
- `docs/meshing/schema-generation-summary.json`

Generation result after nested templates:

- Watertight: 11 top-level tasks, 562 arguments.
- Fault-tolerant: 25 top-level tasks, 635 arguments.
- Watertight: 3/3 compound tasks expose a child template.
- Fault-tolerant: 10/12 compound tasks expose a child template; the two remaining tasks are explicitly blocked.

Real apply verification is recorded in `docs/verification/m8.4-verification.md`. The verified native geometry route uses the reference PMDB file; apply stops before surface or volume mesh generation.

### Remaining PyFluent API Limitation

Two Fault-tolerant compound tasks currently raise `RecursionError` while PyFluent creates their command arguments:

- Identify Construction Surfaces
- Create Local Refinement Regions

They are retained in the schema as explicit unavailable-argument markers. They must not be filled with guessed fields. These tasks require either a future PyFluent fix or a workflow-reference-derived schema with readback verification before they can be safely exposed for editing.
