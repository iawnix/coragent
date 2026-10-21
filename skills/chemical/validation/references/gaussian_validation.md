> The XYZ runner supports opt, sp and opt-sp. The explicit GJF runner also accepts none, opt, frequency, minimum, saddle and irc checks; these do not establish mode character or endpoint identity.

# Gaussian Validation

Verify the collected primary Gaussian output before adding map research notes.

## Program And Intent

Check normal termination, route, method/basis, charge, multiplicity,
solvation/environment, dispersion, grid, SCF treatment, optimization and
frequency keywords, constraints, resources, and material warnings against the
immutable calculation intent. Reject malformed input before remote submission
when the adapter can determine it.

## Stationary Point

Keep normal termination, stationary-point confirmation, optimization
convergence, imaginary-frequency count, and method agreement as separate
research notes. For an ordinary first-order saddle, exactly one imaginary
frequency is necessary. Record the frequency, displacement, and visualization
as distinct source-backed values; relate the displacement to the claimed bond
changes before treating it as a reaction-coordinate fact.

## Relaxed Scan

For a separately implemented Gaussian scan, verify that the route contains a supported `Scan` or
`ModRedundant` scan directive, the requested coordinate and point count are
present in the immutable intent, and the parsed profile has the expected
number of points with energies and coordinates. A complete scan is an energy
profile, not a transition-state validation; a profile maximum is only a
candidate for later saddle-point work.

## Limits And Conditions

Record the observations, scientific criteria, unresolved questions and next steps with research_update using the existing node_id and a note. Publish a reusable conclusion with research_result, citing collected materials and stating limitations. A completed computation does not establish a scientific conclusion.

Failure recovery: inspect the selected calculation section's primary diagnostic before secondary termination signals. `irc_hessian_missing` calls for a supported Hessian source (CalcFC, ReadCartesianFC with compatible checkpoint data, or FCCards), not ReadFC. `irc_corrector_limit` warrants inspecting the last valid point, step size and corrector limit; use a bounded smaller-step or revised-corrector attempt and preserve both directions' coverage. `coordinate_transform` calls for inspecting atom correspondence, close contacts and endpoint alignment before choosing revised seeds or a suitable coordinate method. A segmentation signal after these messages does not by itself establish a hardware fault. Retain failed inputs/logs and use new attempt identities for changed inputs. Partial IRC trajectories do not establish endpoint connectivity.
