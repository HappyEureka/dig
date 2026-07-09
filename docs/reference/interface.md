# Reference: the DIG interface

`DIGAgent` -- wrap any agent so its activity records into a DIG. It owns a
mailbox-compatible buffer of delivered, unconsumed events; the DIG only observes
that. See the [DIGAgent guide](../guide/interface/agent.md) for the design rationale and
the minimal example.

```{eval-rst}
.. autoclass:: dig.interface.DIGAgent
   :members:

.. autoclass:: dig.agent.DIGAgentEntity
   :members:
```
