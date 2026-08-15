import json
import time
import redis
from django.conf import settings
from celery import shared_task

from common.constants import (
    PROVISIONING_STEPS,
    REDIS_PROVISIONING_CHANNEL_PREFIX,
    REDIS_TASK_KEY_PREFIX,
)


def get_redis_client():
    return redis.from_url(settings.REDIS_URL)


def _update_task_in_redis(r, task_id, task_data):
    """Store the full task state in Redis."""
    key = f"{REDIS_TASK_KEY_PREFIX}{task_id}"
    r.set(key, json.dumps(task_data), ex=86400)  # expire after 24 hours


def _publish_step_update(r, task_id, step_update):
    """Publish step progress to the Redis provisioning channel."""
    channel = f"{REDIS_PROVISIONING_CHANNEL_PREFIX}{task_id}"
    r.publish(channel, json.dumps(step_update))


@shared_task(bind=True)
def run_onboard_task(self, task_id, email, team_id=None, role='MEMBER'):
    """
    Simulate onboarding a new user across services.
    Steps: Google Workspace, Slack, Figma, GitHub, Notion
    """
    r = get_redis_client()

    steps = [{'service': s, 'status': 'pending'} for s in PROVISIONING_STEPS]

    task_data = {
        'task_id': str(task_id),
        'email': email,
        'task_type': 'onboard',
        'status': 'processing',
        'steps': steps,
    }
    _update_task_in_redis(r, task_id, task_data)

    try:
        for i, step in enumerate(steps):
            # Mark current step as processing
            steps[i]['status'] = 'processing'
            task_data['steps'] = steps
            _update_task_in_redis(r, task_id, task_data)
            _publish_step_update(r, task_id, {
                'task_id': str(task_id),
                'step': step['service'],
                'step_status': 'processing',
                'overall_status': 'processing',
                'steps': steps,
            })

            # Simulate work
            time.sleep(2)

            # Mark step as done
            steps[i]['status'] = 'done'
            task_data['steps'] = steps
            _update_task_in_redis(r, task_id, task_data)
            _publish_step_update(r, task_id, {
                'task_id': str(task_id),
                'step': step['service'],
                'step_status': 'done',
                'overall_status': 'processing',
                'steps': steps,
            })

        # All steps done — update task status in DB and Redis
        task_data['status'] = 'done'
        _update_task_in_redis(r, task_id, task_data)
        _publish_step_update(r, task_id, {
            'task_id': str(task_id),
            'step': None,
            'step_status': None,
            'overall_status': 'done',
            'steps': steps,
        })

        # Update DB record
        from apps.provisioning.models import ProvisioningTask
        ProvisioningTask.objects.filter(task_id=task_id).update(
            status='done',
            steps=steps,
        )

    except Exception as exc:
        # Mark task as failed
        task_data['status'] = 'failed'
        _update_task_in_redis(r, task_id, task_data)
        _publish_step_update(r, task_id, {
            'task_id': str(task_id),
            'step': None,
            'step_status': None,
            'overall_status': 'failed',
            'steps': steps,
        })

        from apps.provisioning.models import ProvisioningTask
        ProvisioningTask.objects.filter(task_id=task_id).update(
            status='failed',
            steps=steps,
        )
        raise exc


@shared_task(bind=True)
def run_offboard_task(self, task_id, email, figma_transfer_to=None):
    """
    Simulate offboarding a user from services.
    Steps: Google Workspace, Slack, Figma, GitHub, Notion
    """
    r = get_redis_client()

    steps = [{'service': s, 'status': 'pending'} for s in PROVISIONING_STEPS]

    task_data = {
        'task_id': str(task_id),
        'email': email,
        'figma_transfer_to': figma_transfer_to,
        'task_type': 'offboard',
        'status': 'processing',
        'steps': steps,
    }
    _update_task_in_redis(r, task_id, task_data)

    try:
        for i, step in enumerate(steps):
            steps[i]['status'] = 'processing'
            task_data['steps'] = steps
            _update_task_in_redis(r, task_id, task_data)
            _publish_step_update(r, task_id, {
                'task_id': str(task_id),
                'step': step['service'],
                'step_status': 'processing',
                'overall_status': 'processing',
                'steps': steps,
            })

            time.sleep(2)

            # Special handling for Figma: simulate asset transfer
            if step['service'] == 'Figma' and figma_transfer_to:
                time.sleep(1)

            steps[i]['status'] = 'done'
            task_data['steps'] = steps
            _update_task_in_redis(r, task_id, task_data)
            _publish_step_update(r, task_id, {
                'task_id': str(task_id),
                'step': step['service'],
                'step_status': 'done',
                'overall_status': 'processing',
                'steps': steps,
            })

        task_data['status'] = 'done'
        _update_task_in_redis(r, task_id, task_data)
        _publish_step_update(r, task_id, {
            'task_id': str(task_id),
            'step': None,
            'step_status': None,
            'overall_status': 'done',
            'steps': steps,
        })

        from apps.provisioning.models import ProvisioningTask
        ProvisioningTask.objects.filter(task_id=task_id).update(
            status='done',
            steps=steps,
        )

    except Exception as exc:
        task_data['status'] = 'failed'
        _update_task_in_redis(r, task_id, task_data)
        _publish_step_update(r, task_id, {
            'task_id': str(task_id),
            'step': None,
            'step_status': None,
            'overall_status': 'failed',
            'steps': steps,
        })

        from apps.provisioning.models import ProvisioningTask
        ProvisioningTask.objects.filter(task_id=task_id).update(
            status='failed',
            steps=steps,
        )
        raise exc
