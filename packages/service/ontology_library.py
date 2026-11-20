"""CoSpace host adapter for the portable, shared draft definition library."""
from packages.ontology.kernel import builtin_catalog


def ontology_library():
    # No jobs, scenes, workspace stores or external service access is needed.
    # Authentication/subscription policies belong to the host HTTP boundary.
    return builtin_catalog().describe()
