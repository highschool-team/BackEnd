from decimal import Decimal
from datetime import datetime, timedelta, timezone

from django.db.models import Sum, Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from common.permissions import IsDevOpsOrTechLead, IsPartLeadOrAbove
from apps.teams.models import Team
from apps.authentication.models import User
from .models import UsageLog


class DashboardOverviewView(APIView):
    permission_classes = [IsDevOpsOrTechLead]

    @extend_schema(summary='전사 예산 현황', tags=['Dashboard'])
    def get(self, request):
        teams = Team.objects.prefetch_related('providers').all()

        company_budget = teams.aggregate(total=Sum('budget'))['total'] or Decimal('0')
        blocked_teams_count = teams.filter(status='BLOCKED').count()

        teams_summary = []
        total_spent = Decimal('0')
        total_allocated = Decimal('0')

        for team in teams:
            spent = team.spent
            allocated = team.allocated
            total_spent += spent
            total_allocated += allocated
            teams_summary.append({
                'team_id': team.id,
                'team_name': team.name,
                'budget': team.budget,
                'spent': spent,
                'allocated': allocated,
                'status': team.status,
            })

        return Response({
            'company_budget': company_budget,
            'total_spent': total_spent,
            'total_allocated': total_allocated,
            'blocked_teams': blocked_teams_count,
            'teams_summary': teams_summary,
        })


class TeamUsageView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='팀 사용량 조회',
        parameters=[
            OpenApiParameter('period', OpenApiTypes.STR, enum=['day', 'week', 'month'], default='week'),
            OpenApiParameter('metric', OpenApiTypes.STR, enum=['cost', 'calls'], default='cost'),
        ],
        tags=['Dashboard'],
    )
    def get(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        user = request.user

        # Access control
        if user.role not in ('TECHLEAD', 'DEVOPS'):
            if user.role in ('PARTLEAD', 'MEMBER'):
                if str(user.team_id) != str(pk):
                    return Response(
                        {'error': 'forbidden', 'message': 'You can only view your own team usage.'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                return Response(
                    {'error': 'forbidden', 'message': 'Access denied.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        period = request.query_params.get('period', 'week')
        metric = request.query_params.get('metric', 'cost')

        now = datetime.now(timezone.utc)

        if period == 'day':
            start_time = now - timedelta(hours=24)
            labels = [f"{h:02d}:00" for h in range(24)]
            data_points = 24
            group_format = 'hour'
        elif period == 'week':
            start_time = now - timedelta(days=7)
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            # Generate last 7 days in order
            labels = []
            for i in range(6, -1, -1):
                day = now - timedelta(days=i)
                labels.append(day_names[day.weekday()])
            data_points = 7
            group_format = 'day'
        elif period == 'month':
            start_time = now - timedelta(days=30)
            labels = []
            for i in range(29, -1, -1):
                day = now - timedelta(days=i)
                labels.append(day.strftime('%m/%d'))
            data_points = 30
            group_format = 'day_date'
        else:
            return Response(
                {'error': 'invalid_period', 'message': "period must be one of: day, week, month"},
                status=status.HTTP_400_BAD_REQUEST
            )

        logs = UsageLog.objects.filter(team=team, created_at__gte=start_time)

        if metric == 'cost':
            chart_data = self._aggregate_cost(logs, period, now, labels, data_points, group_format)
        elif metric == 'calls':
            chart_data = self._aggregate_calls(logs, period, now, labels, data_points, group_format)
        else:
            return Response(
                {'error': 'invalid_metric', 'message': "metric must be one of: cost, calls"},
                status=status.HTTP_400_BAD_REQUEST
            )

        total_cost = logs.aggregate(total=Sum('cost'))['total'] or Decimal('0')
        total_calls = logs.count()
        total_input = logs.aggregate(total=Sum('input_tokens'))['total'] or 0
        total_output = logs.aggregate(total=Sum('output_tokens'))['total'] or 0

        return Response({
            'team_id': str(team.id),
            'team_name': team.name,
            'period': period,
            'metric': metric,
            'chart_data': {
                'labels': labels,
                'values': chart_data,
            },
            'summary': {
                'total_cost': total_cost,
                'total_calls': total_calls,
                'total_input_tokens': total_input,
                'total_output_tokens': total_output,
            }
        })

    def _aggregate_cost(self, logs, period, now, labels, data_points, group_format):
        values = [Decimal('0')] * data_points
        for log in logs:
            idx = self._get_index(log.created_at, period, now, data_points)
            if 0 <= idx < data_points:
                values[idx] += log.cost
        return [float(v) for v in values]

    def _aggregate_calls(self, logs, period, now, labels, data_points, group_format):
        values = [0] * data_points
        for log in logs:
            idx = self._get_index(log.created_at, period, now, data_points)
            if 0 <= idx < data_points:
                values[idx] += 1
        return values

    def _get_index(self, created_at, period, now, data_points):
        if period == 'day':
            # Index = hour of the day (0-23)
            # We show the last 24 hours; index corresponds to the hour label
            start = now - timedelta(hours=24)
            diff_hours = int((created_at - start).total_seconds() // 3600)
            return diff_hours
        elif period == 'week':
            # Index = how many days ago (0=6 days ago, 6=today)
            diff_days = (now.date() - created_at.date()).days
            idx = (data_points - 1) - diff_days
            return idx
        elif period == 'month':
            # Index = 0 is 29 days ago, 29 is today
            diff_days = (now.date() - created_at.date()).days
            idx = (data_points - 1) - diff_days
            return idx
        return -1


class TeamMembersUsageView(APIView):
    permission_classes = [IsPartLeadOrAbove]

    @extend_schema(summary='팀원별 사용량', tags=['Dashboard'])
    def get(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        user = request.user

        # PARTLEAD can only see their own team
        if user.role == 'PARTLEAD' and str(user.team_id) != str(pk):
            return Response(
                {'error': 'forbidden', 'message': 'You can only view your own team member usage.'},
                status=status.HTTP_403_FORBIDDEN
            )

        members = User.objects.filter(team=team)
        result = []

        for member in members:
            logs = UsageLog.objects.filter(user=member, team=team)
            agg = logs.aggregate(
                total_cost=Sum('cost'),
                total_calls=Count('id'),
                total_input=Sum('input_tokens'),
                total_output=Sum('output_tokens'),
            )
            result.append({
                'user_id': member.id,
                'email': member.email,
                'total_cost': agg['total_cost'] or Decimal('0'),
                'total_calls': agg['total_calls'] or 0,
                'total_input_tokens': agg['total_input'] or 0,
                'total_output_tokens': agg['total_output'] or 0,
            })

        return Response({
            'team_id': str(team.id),
            'team_name': team.name,
            'members': result,
        })
