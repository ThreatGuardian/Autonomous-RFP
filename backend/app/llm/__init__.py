"""Language-model agents (Claude).

Each pipeline agent that uses a language model keeps a rule-based path. The model is
asked for structured output or works through tools whose results are computed by this
code, and every value it returns is validated before it is used: prices against the
margin floor, products against the catalogue, client-facing text against leaks of
internal figures. When the model is not configured or a call fails, the agent falls
back to its rules and says so in the stage log.
"""
