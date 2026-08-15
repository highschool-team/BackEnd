from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """Custom exception handler that formats errors consistently."""
    response = exception_handler(exc, context)

    if response is not None:
        error_data = {
            'error': 'request_failed',
            'message': '',
            'details': response.data,
        }

        if response.status_code == status.HTTP_400_BAD_REQUEST:
            error_data['error'] = 'validation_error'
            error_data['message'] = 'Request validation failed.'
        elif response.status_code == status.HTTP_401_UNAUTHORIZED:
            error_data['error'] = 'unauthorized'
            error_data['message'] = 'Authentication credentials were not provided or are invalid.'
        elif response.status_code == status.HTTP_403_FORBIDDEN:
            error_data['error'] = 'forbidden'
            error_data['message'] = 'You do not have permission to perform this action.'
        elif response.status_code == status.HTTP_404_NOT_FOUND:
            error_data['error'] = 'not_found'
            error_data['message'] = 'The requested resource was not found.'
        elif response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            error_data['error'] = 'quota_exceeded'
            error_data['message'] = 'API quota has been exceeded.'

        response.data = error_data

    return response
