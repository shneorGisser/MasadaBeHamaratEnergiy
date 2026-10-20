# Backlog (after experiments 1–6)

Order agreed with the user on 2026-10-20. Done items move to `test-log.md`.

1. ~~Import real lab reports as measurement sets~~. Done: `vel/labdata`, plus the import UI in the measurements panel.
2. ~~Automatic explanation of measured-vs-simulated differences~~. Done: `services/diagnose.py` (the per-comparison detectors and the parameter-set probe).
3. **Visual wiring guide.** Requested by the user: "איך לחבר ואיפה איזה כבל".
   * For every study circuit, a step-by-step guide that shows which cable goes from which
     terminal to which, in the order a student wires the bench: supply off first, then the
     current path, then the voltage leads.
   * The same circuit document that drives the schematic and the 3D bench drives the guide,
     so the guide can never contradict the simulation.
   * It is only partly possible until there are photos of the real terminal boards. Until then
     it shows the schematic terminal names (A1, F1, U1 …) and highlights wire k of n on the
     schematic and the 3D bench.
4. Word export of the report: Hebrew RTL, David 11, line spacing 1.15, MATLAB/Python code in an appendix.
5. Hysteresis (falling OCC branch) for the synchronous and DC machines.
6. 3D bench modelled on the real equipment. Waits for the photos.
7. Experiment 8 (installation testing: RCD, loop impedance, earthing). The manual is available;
   nothing is started without approval.
8. Cloud deployment (`docs/deploy-cloud-run.md`).
