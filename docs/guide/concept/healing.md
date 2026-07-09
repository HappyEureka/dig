# Healing

A **healer** watches the DIG for one anomaly and emits **interventions**. Healers
read only the interaction graph -- never a task model -- so graph-shaped errors
(orphaned events, duplicated work, deadlock) are detectable. A runtime fires the
hooks and applies interventions when its `apply` flag is set.

DIG coverage means **interaction-lineage coverage**: an activation's backward
lineage reaches the run's root DIG input events. It is not a task-completeness
verdict; task correctness belongs to the environment side.

---

## Minimal use

```python
from dig.heal import default_healers, run_activation_healers

healers = default_healers()

applied = await run_activation_healers(
    dig,
    activation,
    healers,
    apply=True,
)
```

The hook runners are deliberately runtime-agnostic. They run healer hooks, count
each detection on its proposing healer (`healer.detections`; aggregate a roster
with `detection_stats(healers)`), and optionally apply each returned
intervention (application delivers any resulting event itself). Applied
interventions are counted by READING the record
(`intervention_stats(dig)`), never stored on the graph. Applying
an intervention records a normal system activation with
`metadata["dig"]["intervention"]`, so intervention history stays inside the DIG
instead of in a side channel.

---

## `Healer`

**Design.** One healer = one anomaly. Override the hook(s) you need; each returns a
list of `Intervention`s. Application is not a healer method: the hook runners hand
each intervention to `apply_intervention` (`heal/apply.py`), which carries out both
strategies -- so a healer is usually just detection. Override `prepare_intervention`
only when a detail must be decided at application time.

**Definition.**

```python
class Healer(ABC):
    def on_activation_complete(self, dig, activation) -> List[Intervention]: ...
    def on_event_delivered(self, dig, event, recipients) -> List[Intervention]: ...
    def on_idle_tick(self, dig, idle_cycles) -> List[Intervention]: ...
    def prepare_intervention(self, itv, *, dig) -> None: ...   # finalize just before application
```

| hook | fires when |
|---|---|
| `on_activation_complete` | an activation was recorded |
| `on_event_delivered` | an event landed in a mailbox |
| `on_idle_tick` | the runtime is idle (`idle_cycles` consecutive) |

**Pseudocode.**

```text
on activation:  queue += h.on_activation_complete(dig, act)
on delivery:    queue += h.on_event_delivered(dig, ev, recipients)
on idle:        queue += h.on_idle_tick(dig, idle_cycles)
if apply:       for itv in queue: h.prepare_intervention(itv); await apply_intervention(itv)
```

---

## `Intervention`

**Design.** What a healer emits. **annotate** an existing event (inject a message,
optionally reroute) or **create** a new system event. Build with the factories.

**Definition.**

```python
@dataclass
class Intervention:
    label: str            # Intervention.Label value or custom string
    strategy: str         # "annotate" | "create"
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)   # extra context for the runtime
    target_event_id: Optional[str] = None      # annotate
    reroute_to: Optional[List[str]] = None     # annotate
    recipients: Optional[List[str]] = None     # create
    input_event_ids: List[str] = field(default_factory=list) # create

    @classmethod
    def annotate(cls, label, target_event_id, message, *, reroute_to=None, metadata=None): ...
    @classmethod
    def create(cls, label, recipients, message, *, input_event_ids=None, metadata=None): ...
```

**Pseudocode (inside a hook).**

```text
on_activation_complete(dig, activation):              # the hook OrphanEventHealer overrides
    for ev in <events delivered but with no live recipient>:
        return [Intervention.annotate(label=ORPHANED_EVENT, target_event_id=ev.id,
                                      message="reroute back to originator",
                                      reroute_to=[the source agent])]
    return []
```

---

## The bundled healers

All seven are **DIG-only**: they trigger on graph shape alone. Two are
domain-parameterized -- `RepeatedEffortsHealer` and `DependencyWarningHealer`
take a `relevant=` event predicate so a runtime can narrow which events they
watch, and dependency warning takes `is_generator=` for an exact domain
notion of a generator (a runtime can pass its own solution-event predicate
and decompose check; no task vocabulary lives in the healers). With
no predicate, `default_healers()` considers EVERY event: repeated efforts
then fires on any multi-recipient event -- narrow it when broadcasts are
normal in your runtime. The first four read interaction shape; the last three
read backward lineage over root DIG inputs.

| Healer | Hook | Detects |
|---|---|---|
| `OrphanEventHealer` | `on_activation_complete` + `on_idle_tick` | an event no recipient can act on |
| `ExcessiveReroutingHealer` | `on_activation_complete` | an event bounced too many times |
| `RepeatedEffortsHealer` | `on_event_delivered` | two agents doing the same work |
| `DependencyWarningHealer` | `on_event_delivered` | an agent mixing pending partials from distinct problem-generating ancestors |
| `IncompleteCoverageHealer` | `on_activation_complete` | a submission whose DIG lineage misses root input events |
| `MissedSubmissionHealer` | `on_activation_complete` | root input lineage covered but no submit activation recorded |
| `DeadlockHealer` | `on_idle_tick` | everyone waiting on everyone |

**New healer.** Subclass `Healer`, override one hook, return `Intervention`s, and
register it in the runtime's roster. Add the label to `Intervention.Label` only when
the anomaly is a built-in DIG category; custom strings are valid for local/runtime
experiments.
