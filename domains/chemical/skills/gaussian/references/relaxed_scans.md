# Two-dimensional relaxed torsion scans

A missing scan recipe does not imply the solver cannot scan. Use an explicit Gaussian input or a task script submitted through Job Runtime, with the configured Gaussian binding. Check the selected method's constraint syntax before scaling up.

1. Define phi and psi as ordered, one-based atom quadruples in a retained structure; verify the atom order, charge and multiplicity. Record periodic angle conventions and avoid duplicate -180/180 endpoints.
2. Choose the grid and budget before submission: points per axis, methods, optimization limit and retry limit. Validate a small subset, including a boundary point, first.
3. For each pair, construct or rotate a starting geometry and constrain **both** target torsions during optimization. A Gaussian ModRedundant input can freeze the two dihedrals with `D i j k l F` after preparing the intended starting angles. Check the applicable Gaussian version and route; freezing alone does not set a target angle. Independent per-point inputs make retries and provenance explicit. xTB uses its own constraint syntax and must not reuse Gaussian cards.
4. Store target and measured final angles, constraint tolerances, convergence, energy and units, method/basis, starting structure, input digest and Job/Artifact references per point. Normal termination alone does not prove the requested constrained point was obtained.
5. Resume by a manifest keyed by method, grid coordinates and input identity. Reuse only verified converged points with compatible settings; retain failed points as missing and rerun only the selected failures. Do not fill failed cells with plausible values or silently call a sparse grid complete.
6. Compare relative energies **within each method**, subtracting that method's lowest verified grid energy. Label incomplete coverage, interpolation, constrained minima and any unconstrained follow-up separately. Do not rank methods using their raw absolute energies.

Keep scan points as attempts under the same research question. A point failure should not block independent points; changed seeds or settings get new attempt identities. Report coverage against the requested grid before completion.
