import datetime
import boto3

retention_days = 10
regions = ['eu-west-1']
account = 'SUPER ACCOUNT ID'

def lambda_handler(event, _context):
    owner_id = event['account']

    for region in regions:
        print("Lookup EC2 in %s region" % region)
        aws_client = boto3.client('ec2', region_name=region)
        ec2_reservations = aws_client.describe_instances(
                Filters=[
                    {"Name": "tag-value", "Values": ["true"]},
                    {"Name": "tag-key", "Values": ["jobteaser.com/etcd/backup"]},
                ])['Reservations']

        ec2_instances = sum([[i for i in reservation['Instances']] for reservation in ec2_reservations], [])

        for instance in ec2_instances:
            for device in instance['BlockDeviceMappings']:
                if device.get('Ebs', None) is None:
                    continue # Skip non EBS volumes

                volume_id = device['Ebs']['VolumeId']
                instance_id = instance['InstanceId']
                device_name = device['DeviceName']

                print("Trigger snapshot in %s EC2 Instance for %s EBS volume" % (instance_id, volume_id))
                description = "Snapshot of Instances %s on %s" % (instance_id, device_name)
                snapshot = aws_client.create_snapshot(VolumeId=volume_id, Description=description)
                expire_at = datetime.date.today() + datetime.timedelta(days=retention_days).strftime('%Y-%m-%d')

                print("Tag %s snapshot" % snapshot['SnapshotId'])
                aws_client.create_tags(
                        Resources=[snapshot['SnapshotId']],
                        Tags=[
                            {'Key': 'ExpireAt', 'Value': expire_at},
                            {'Key': 'VolumeId', 'Value': volume_id},
                            {'Key': 'InstanceId', 'Value': instance_id},
                            {'Key': 'DeviceName', 'Value': device_name}
                            ]
                        )

        # Maybe create a new lambda to handle deletion
        print("Search expired snapshot")
        today = datetime.date.today().strftime('%Y-%m-%d')
        to_delete_snapshots = aws_client.describe_snapshots(
                # Account filter search to delete snapshot only on the tigger snapshot by the lambda
                OwnerIds=['%s' % account],
                Filters=[
                    {'Name': 'tag-key', 'Values': ['ExpireAt']},
                    {'Name': 'tag-value', 'Values': [today]}
                    ]
                )

        for to_delete_snapshot in to_delete_snapshots:
            print("Delete expire %s snapshot" % snapshot['SnapshotId'])
            aws_client.delete_snapshot(SnapshotId=to_delete_snapshot['SnapshotId'])
