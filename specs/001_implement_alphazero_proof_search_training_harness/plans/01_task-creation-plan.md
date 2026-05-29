# Implementation Plan: Task #1 -- Create Training Harness Sub-Tasks

- **Task**: 1 - Implement AlphaZero proof search training harness
- **Status**: [COMPLETED]
- **Effort**: 2 hours
- **Dependencies**: None
- **Research Inputs**: specs/001_implement_alphazero_proof_search_training_harness/reports/01_team-research.md
- **Artifacts**: plans/01_task-creation-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Task 1 is a meta-task: its purpose is to create the individual sub-tasks needed to build the AlphaZero proof search training harness in BimodalHarness. The team research report synthesized findings from four teammates into a 25-task decomposition across 8 layers, informed by the BimodalLogic task decomposition plan, the corrective-signal team research, and the Logos technical memo. This plan describes the process of validating that task list, presenting it to the user for confirmation/modification, creating all confirmed tasks in state.json and TODO.md with correct dependencies, and committing the result. The plan is complete when all confirmed tasks exist in the task management system with proper dependency chains.

### Research Integration

The team research report (01_team-research.md) produced a synthesized 25-task list across 8 layers:
- Layer 0: Project Foundation (3 tasks: project setup, cross-repo design, data schema)
- Layer 1: Data Pipeline (5 tasks: bridge validation, static ingestion, formula generator, proof trace extraction, PatternKey extractor)
- Layer 2: Value Network (3 tasks: value network, benchmark suite, value-Lean integration)
- Layer 3: Policy Network and Expert Iteration (3 tasks: policy network, neural search, expert iteration loop)
- Layer 4: MCTS (2 tasks: AND/OR MCTS, online training from search trees)
- Layer 5: ModelChecker Alignment (4 tasks: Until/Since, frame classes, ternary task relation, conformance tests)
- Layer 6: Dual Verification (3 tasks: Z3 countermodel generator, countermodel-to-tensor, dual training integration)
- Layer 7: Production and Evaluation (2 tasks: data export pipeline, experiment tracking)

Four open questions remain for user resolution:
1. Whether ModelChecker tasks (18-21) should be tracked here or in Logos/ModelChecker
2. Whether Lean-side coordination tasks are needed
3. Priority scope (value-network-first vs full pipeline)
4. GPU availability and compute constraints

The BimodalLogic task decomposition (6 sub-tasks across 6 phases) and corrective-signal research (three-tier strategy) were incorporated into the synthesized list. The technical memo confirms BimodalHarness is the Stage 1 revenue pipeline (verified synthetic training data).

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found. The roadmap_path was specified but the file does not exist at specs/ROADMAP.md. Task creation will proceed without roadmap alignment.

## Goals & Non-Goals

**Goals**:
- Validate the 25-task synthesized list from team research against source documents
- Present the complete task list to the user for review, modification, and confirmation
- Resolve open questions (ModelChecker ownership, priority scope, compute constraints)
- Create all confirmed tasks in state.json and TODO.md with correct task types, effort estimates, descriptions, and dependency chains
- Apply topological ordering so foundational tasks receive lower task numbers
- Commit the batch of created tasks

**Non-Goals**:
- Implementing any component of the training harness (each sub-task handles its own lifecycle)
- Making final architecture decisions (each sub-task's research/plan phases decide)
- Creating ROADMAP.md (that is a separate concern)
- Modifying any code in BimodalLogic or ModelChecker projects

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| User rejects significant portion of task list | M | M | Present tasks by layer with clear rationale; allow selective inclusion |
| Dependency graph has cycles after user modifications | H | L | Validate with cycle detection before writing state; prompt user to resolve |
| 25 tasks overwhelms state.json/TODO.md at once | M | L | Batch insertion preserves ordering; user can scope to subset of layers |
| ModelChecker tasks create cross-repo confusion | M | M | Ask user explicitly; recommend keeping in BimodalHarness with clear notes about target repo |
| Task number collisions if user creates tasks between phases | L | L | Phase 2 reads current next_project_number; batch creation is atomic |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2 | 1 |
| 3 | 3 | 2 |
| 4 | 4 | 3 |
| 5 | 5 | 4 |

Phases within the same wave can execute in parallel.

---

### Phase 1: Validate and Prepare Task List [COMPLETED]

**Goal**: Read the synthesized task list from the research report, cross-reference against source documents, and prepare a structured task proposal for user review.

**Tasks**:
- [ ] Read the synthesized 25-task list from `specs/001_implement_alphazero_proof_search_training_harness/reports/01_team-research.md`
- [ ] Cross-reference each task against the BimodalLogic task decomposition plan to verify coverage of the original 6 sub-task scope
- [ ] Cross-reference against the corrective-signal research to verify dual verification tasks are properly included
- [ ] Cross-reference against the technical memo to verify Stage 1 revenue pipeline alignment
- [ ] Verify each task has: title, description, task_type, effort estimate (S/M/L/XL), and dependency list
- [ ] Identify any gaps or redundancies in the synthesized list
- [ ] Prepare a structured summary table with all 25 tasks, organized by layer, showing dependencies

**Timing**: 30 minutes

**Depends on**: none

**Files to modify**:
- None (read-only validation phase)

**Verification**:
- All 25 tasks have been validated against source documents
- A complete task table is ready for user presentation

---

### Phase 2: Present Task List and Resolve Open Questions [COMPLETED]

**Goal**: Present the validated task list to the user, resolve the 4 open questions, and obtain confirmation on which tasks to create.

**Tasks**:
- [ ] Present the 25-task summary table to the user organized by layer
- [ ] Ask user to resolve open questions:
  - ModelChecker tasks (18-21): track here or in Logos/ModelChecker?
  - Lean-side coordination: are additional tasks needed?
  - Priority scope: value-network-first (Layers 0-2) or full pipeline (all layers)?
  - GPU availability: affects effort estimates for Layers 3-4
- [ ] Allow user to modify task descriptions, add/remove tasks, adjust effort estimates
- [ ] Allow user to adjust dependencies based on their preferred execution strategy
- [ ] Obtain explicit "Yes, create tasks" confirmation before proceeding (per multi-task creation standard)

**Timing**: 30 minutes

**Depends on**: 1

**Files to modify**:
- None (interactive phase; no files changed until user confirms)

**Verification**:
- User has explicitly confirmed the final task list
- All 4 open questions are resolved
- Final task count and dependency graph are determined

---

### Phase 3: Create Tasks in State Management [COMPLETED]

**Goal**: Insert all confirmed tasks into state.json and TODO.md with correct dependencies, task types, and effort estimates using batch insertion.

**Tasks**:
- [ ] Read current state.json to get `next_project_number` (currently 2)
- [ ] Apply topological sort (Kahn's algorithm) to the confirmed dependency graph so foundational tasks get lower numbers
- [ ] Assign task numbers starting from `next_project_number`, following topological order
- [ ] Remap all internal dependency references to use the assigned task numbers
- [ ] Build state.json entries for all tasks with fields: project_number, project_name, status ("not_started"), task_type, dependencies, created, last_updated
- [ ] Build TODO.md entries for all tasks with fields: title, effort, status ([NOT STARTED]), task type, dependencies, description (including seed research brief from the research report)
- [ ] Write state.json first (machine truth), then TODO.md (user-facing)
- [ ] Update `next_project_number` to max(assigned_numbers) + 1
- [ ] Create task directories: `specs/{NNN}_{SLUG}/` for each task

**Timing**: 30 minutes

**Depends on**: 2

**Files to modify**:
- `specs/state.json` -- Add all confirmed task entries to active_projects array; update next_project_number
- `specs/TODO.md` -- Add all confirmed task entries after `## Tasks` heading using batch insertion
- `specs/{NNN}_{SLUG}/` -- Create directories for each new task (lazy creation)

**Verification**:
- state.json and TODO.md are synchronized (same task count, same dependencies)
- All dependency references point to valid task numbers
- No circular dependencies exist
- next_project_number is correctly updated
- Task directories exist

---

### Phase 4: Validate and Visualize Dependency Graph [COMPLETED]

**Goal**: Verify the integrity of the created tasks and display the dependency graph for user review.

**Tasks**:
- [ ] Re-read state.json and validate all tasks are present with correct dependencies
- [ ] Run cycle detection on the dependency graph to confirm no cycles
- [ ] Validate that all dependency targets exist as tasks
- [ ] Generate a layered DAG visualization of the dependency graph
- [ ] Display summary: total tasks created, layers covered, critical path, parallel execution opportunities
- [ ] Mark Task 1 status as [EXPANDED] in state.json (it has been decomposed into sub-tasks)

**Timing**: 15 minutes

**Depends on**: 3

**Files to modify**:
- `specs/state.json` -- Update Task 1 status to "expanded"
- `specs/TODO.md` -- Update Task 1 status to [EXPANDED]

**Verification**:
- Dependency graph is cycle-free
- All task numbers referenced in dependencies exist
- Task 1 is marked [EXPANDED]

---

### Phase 5: Commit Task Entries [COMPLETED]

**Goal**: Create a git commit capturing all new tasks.

**Tasks**:
- [ ] Run `git status` to verify staged files
- [ ] Run `git diff` to review changes
- [ ] Stage all modified files: specs/state.json, specs/TODO.md, and new task directories
- [ ] Create commit with message: `task 1: create {N} sub-tasks for training harness`
- [ ] Include session ID in commit body

**Timing**: 5 minutes

**Depends on**: 4

**Files to modify**:
- Git staging area only

**Verification**:
- Commit created successfully
- Commit message follows convention: `task {N}: {action}`
- Session ID included in commit body

---

## Testing & Validation

- [ ] state.json `next_project_number` matches max(task_numbers) + 1
- [ ] Every task in state.json has a corresponding entry in TODO.md
- [ ] Every task in TODO.md has a corresponding entry in state.json
- [ ] All dependency references in state.json point to valid task numbers
- [ ] All dependency references in TODO.md match state.json
- [ ] No circular dependencies in the graph
- [ ] Task types are correctly set (python for ML tasks, general for design tasks)
- [ ] Effort estimates are present for all tasks
- [ ] Task directories `specs/{NNN}_{SLUG}/` exist for all created tasks
- [ ] Git commit is clean (no unstaged changes to specs/)

## Artifacts & Outputs

- `specs/001_implement_alphazero_proof_search_training_harness/plans/01_task-creation-plan.md` (this file)
- Updated `specs/state.json` with 25 (or user-confirmed count) new task entries
- Updated `specs/TODO.md` with corresponding task entries
- New task directories `specs/{NNN}_{SLUG}/` for each created task
- Git commit capturing all task entries

## Rollback/Contingency

This plan creates task entries only; no code is modified. If the task list proves incorrect after initial research rounds on sub-tasks:
- Individual tasks can be abandoned via `/task --abandon N`
- Dependencies can be adjusted by editing state.json and TODO.md
- The entire batch can be reverted via `git revert` on the commit
- If user wants to start over, `git reset` to the pre-creation commit and re-run `/implement 1`
