"""CoSpace authentication policy and persistence for the portable workbench."""
from packages.ontology.authoring_sqlite import SQLiteAuthoringPort
from packages.ontology.kernel.workbench import DefinitionWorkbench as PortableWorkbench


class DefinitionWorkbench(PortableWorkbench):
    def __init__(self, root, scope, actor, can_manage):
        def authorize(request_scope, principal, action):
            return request_scope == scope and principal == actor and (action == 'read' or can_manage)

        super().__init__(SQLiteAuthoringPort(root), scope, actor, authorize=authorize)
