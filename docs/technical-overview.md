# Optimization overview for stakeholders

The allocator solves the three activities as one mathematical problem. Hard constraints guarantee complete, unique assignment and balanced group sizes. A pair indicator captures whether two participants meet in each activity. The solver first seeks assignments with fewer repeated pairs, which increases the number of different colleagues encountered because total teammate seats are fixed. It then uses configured, normalized factor penalties to prevent group compositions from drifting unnecessarily far from the cohort composition.

Independent random grouping cannot reason about all earlier pairings or prove constraint satisfaction and quality simultaneously. CP-SAT searches combinations systematically, preserves locks exactly, returns an honest solver status, and makes every objective measurable. The deterministic seed makes demonstrations and tests reproducible.

The engine is deliberately factor-agnostic: it reads factor definitions and source-column values from configuration. A new categorical spreadsheet field therefore becomes optimizable data without adding field-specific code. New mathematical strategies can be added behind the same strategy interface.
