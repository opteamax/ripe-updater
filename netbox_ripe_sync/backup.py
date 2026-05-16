import logging

from .config import get_config

logger = logging.getLogger('netbox.plugins.ripe_sync')


class BackupManager:
    """Stores pre-modification snapshots of RIPE objects in S3."""

    def __init__(self) -> None:
        self._s3 = None

        if get_config('s3_backup_enabled'):
            try:
                import boto3
                self._s3 = boto3.client(
                    service_name='s3',
                    endpoint_url=get_config('s3_endpoint_url'),
                    aws_access_key_id=get_config('s3_access_key'),
                    aws_secret_access_key=get_config('s3_secret_key'),
                )
                bucket = get_config('s3_bucket')
                try:
                    self._s3.create_bucket(Bucket=bucket)
                    logger.info(f'Created S3 bucket {bucket}')
                except self._s3.exceptions.BucketAlreadyOwnedByYou:
                    pass
                except Exception as exc:
                    if 'BucketAlreadyExists' not in str(exc):
                        raise
            except ImportError:
                logger.warning('boto3 not installed — S3 backup disabled')
                self._s3 = None

    def put(self, filename: str, content: str) -> None:
        if self._s3 is None:
            return
        bucket = get_config('s3_bucket')
        try:
            self._s3.put_object(Bucket=bucket, Key=filename, Body=content)
            logger.info(f'Backed up {filename} to S3')
        except Exception as exc:
            logger.warning(f'S3 backup failed for {filename}: {exc}')

    def get(self, filename: str) -> bytes:
        if self._s3 is None:
            return b''
        try:
            return self._s3.get_object(
                Bucket=get_config('s3_bucket'), Key=filename
            )['Body'].read()
        except Exception as exc:
            logger.warning(f'S3 get failed for {filename}: {exc}')
            return b''

    def list(self) -> list[str]:
        if self._s3 is None:
            return []
        try:
            resp = self._s3.list_objects_v2(Bucket=get_config('s3_bucket'))
            return [obj['Key'] for obj in resp.get('Contents', [])]
        except Exception as exc:
            logger.warning(f'S3 list failed: {exc}')
            return []
