import json
from kafka import KafkaProducer

from .config import settings


class KafkaEventQueue:
    def __init__(self):
        self.topic = settings.kafka_topic
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=[settings.kafka_bootstrap_servers],
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            self.enabled = True
        except Exception:
            self.producer = None
            self.enabled = False

    def publish(self, event: dict):
        if not self.enabled:
            return

        try:
            self.producer.send(self.topic, event)
            self.producer.flush()
        except Exception:
            pass
