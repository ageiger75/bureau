"""CEO Performance Cockpit — performance model, analytics and data source.

The layering is deliberate and matches the build brief §35 Phase 6:

    data source -> normalised performance model -> analytics engine -> interface

`source.py` is the only module that knows where numbers come from. Everything above it
works on the normalised model, so replacing mock data with a real warehouse is a change
in one file rather than a rewrite.
"""
