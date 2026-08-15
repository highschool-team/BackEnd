from rest_framework.permissions import BasePermission


class IsTechLead(BasePermission):
    """Allow access only to users with TECHLEAD role."""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == 'TECHLEAD'
        )


class IsPartLeadOrAbove(BasePermission):
    """Allow access to TECHLEAD and PARTLEAD roles."""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ('TECHLEAD', 'PARTLEAD')
        )


class IsTeamMember(BasePermission):
    """
    Allow access if the user belongs to the requested team.
    Checks that request.user.team_id matches the team id in the URL kwargs.
    TechLeads bypass the team check.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == 'TECHLEAD':
            return True
        team_id = view.kwargs.get('pk') or view.kwargs.get('team_id')
        if team_id is None:
            return False
        return str(request.user.team_id) == str(team_id)


class IsDevOpsOrTechLead(BasePermission):
    """Allow access to DEVOPS and TECHLEAD roles."""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ('DEVOPS', 'TECHLEAD')
        )


class IsTeamMemberOrAbove(BasePermission):
    """
    Allow access if the user is TECHLEAD, PARTLEAD of the team,
    or a MEMBER of the team.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == 'TECHLEAD':
            return True
        team_id = view.kwargs.get('pk') or view.kwargs.get('team_id')
        if team_id is None:
            return False
        return str(request.user.team_id) == str(team_id)
