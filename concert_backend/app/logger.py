import logging
import json
from contextvars import ContextVar
from datetime import datetime, timezone

# Context variables for observability
request_id_var = ContextVar("request_id", default=None)
session_id_var = ContextVar("session_id", default=None)
user_id_var = ContextVar("user_id", default=None)
agent_name_var = ContextVar("agent_name", default=None)
booking_id_var = ContextVar("booking_id", default=None)


class JSONLogFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context var values
        req_id = request_id_var.get()
        if req_id:
            log_record["request_id"] = req_id
            
        sess_id = session_id_var.get()
        if sess_id:
            log_record["session_id"] = sess_id
            
        uid = user_id_var.get()
        if uid:
            log_record["user_id"] = uid
            
        agent = agent_name_var.get()
        if agent:
            log_record["agent"] = agent
            
        bid = booking_id_var.get()
        if bid:
            log_record["booking_id"] = bid

        # Exception details
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def setup_logger():
    # Remove all existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    handler = logging.StreamHandler()
    formatter = JSONLogFormatter()
    handler.setFormatter(formatter)
    
    # Configure root logger
    logging.root.setLevel(logging.INFO)
    logging.root.addHandler(handler)
    
    # Silence third-party noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

# Initialize on import
setup_logger()
