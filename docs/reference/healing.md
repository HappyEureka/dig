# Reference: healing

`Healer` + `Intervention` -- watch the DIG, detect graph-shaped errors, and emit
interventions mid-run. See the [Healing guide](../guide/concept/healing.md) for the
design rationale and pseudocode.

```{eval-rst}
.. autoclass:: dig.heal.Healer
   :members:
.. autoclass:: dig.heal.Intervention
   :members:
.. autofunction:: dig.heal.apply_intervention
.. autofunction:: dig.heal.default_healers
.. autofunction:: dig.heal.detection_stats
.. autofunction:: dig.heal.intervention_stats
.. autofunction:: dig.heal.run_activation_healers
.. autofunction:: dig.heal.run_event_healers
.. autofunction:: dig.heal.run_idle_healers
```
