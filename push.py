# File: push.py
# Author: Hongjian Zhu
# Date: Oct 2, 2023
# Description: see below

"""
This function will post test result using AWS SNS Service; will require pre-defined AWS SNS Topics and download rootkey.csv to the same file
Returns:
    None
"""
import boto3
import pandas as pd
import os
from botocore.exceptions import ClientError
import logging,coloredlogs

######################################################
logger = logging.getLogger(__name__)
coloredlogs.install(level='DEBUG', logger=logger, fmt='%(asctime)s %(hostname)s %(levelname)s %(message)s')
current_folder = os.getcwd()
csv_path = current_folder+'\\rootkey.csv'
try:
    df = pd.read_csv(csv_path)
    AK = str(df['Access key ID'][0])
    SK = str(df['Secret access key'][0])
    email = str(df['Email'])
    region = 'ca-central-1'  # central Canada Server
except FileNotFoundError as e:
    logger.info("Unable to locate rootkey.csv, aws sns service disabled")

class SnsWrapper:
    def __init__(self,snsResource): 
        self.sns_resource = snsResource
        
    def create_topic(self,name):
        try:
            topic = self.sns_resource.create_topic(Name=name)
            logger.info("Create new topic")
        except ClientError:
            logger.exception("Fail to create new topic {}".format(name))
            raise
        else:
            return topic
    
    def subscribe(self,topic,protocol,endpoint):
        try:
            subscribe = topic.subscribe(
                Protocol = protocol, Endpoint = endpoint, ReturnSubscriptionArn = True
            )
            logger.info('Subscribe success')
        except ClientError:
            logger.exception('Subscribe fail')
            raise
        else:
            return subscribe
    
    def push_message(self,email,message):
        try:
            targetSns = "arn:aws:sns:ca-central-1:644115212646:AcuTextPush"
            response = self.sns_resource.publish(TopicArn = targetSns, Message = message, MessageAttributes={'email': {'DataType': 'String', 'StringValue': df['Email'][0]}})
            message_id = response['MessageId']

            logger.info("Send message to {}".format(df['Email'][0]))
        except ClientError:
            logger.exception("Send message Failure")
        else:
            return message_id
        
    def list_subscriptions(self, topic=None):
        """
        Lists subscriptions for the current account, optionally limited to a
        specific topic.

        :param topic: When specified, only subscriptions to this topic are returned.
        :return: An iterator that yields the subscriptions.
        """
        try:
            if topic is None:
                subs_iter = self.sns_resource.subscriptions.all()
            else:
                subs_iter = topic.subscriptions.all()
            logger.info("Got subscriptions.")
        except ClientError:
            logger.exception("Couldn't get subscriptions.")
            raise
        else:
            return subs_iter
        
    def delete_subscription(self,subscription):
        """
        Unsubscribes and deletes a subscription.
        """
        try:
            subscription.delete()
            logger.info("Deleted subscription %s.", subscription.arn)
        except ClientError:
            logger.exception("Couldn't delete subscription %s.", subscription.arn)
            raise
        
    def delete_topic(self,topic):
        try:
            topic.delete()
            logger.info('Delete topic {}'.format(topic.arn))
        except ClientError:
            logger.exception("Counldn't delete such topic")
            raise
         
def run(message):
    global email
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        if AK is not None:
            sns_wrapper = SnsWrapper(boto3.client('sns',aws_access_key_id=AK,aws_secret_access_key = SK, region_name = region))
            sns_wrapper.push_message(email,message)
    except NameError:
        logger.warning('AWS SNS disabled...')
        
if __name__ == '__main__':
    run('TEST DURATION TIME MESSAGE CONTEXT')