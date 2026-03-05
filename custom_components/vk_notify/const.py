"""Constants for the VK Notify integration."""

DOMAIN = "vk_notify"

SERVICE_SEND_MESSAGE = "send_message"
CONF_CONFIG_ENTRY_ID = "config_entry_id"

CONF_ACCESS_TOKEN = "access_token"
CONF_GROUP_ID = "group_id"
CONF_RECIPIENT_ID = "recipient_id"
CONF_RECEIVE_MODE = "receive_mode"
CONF_WEBHOOK_SECRET = "webhook_secret"
CONF_CONFIRMATION_CODE = "confirmation_code"

RECEIVE_MODE_SEND_ONLY = "send_only"
RECEIVE_MODE_WEBHOOK = "webhook"
RECEIVE_MODES = [RECEIVE_MODE_SEND_ONLY, RECEIVE_MODE_WEBHOOK]

VK_API_BASE_URL = "https://api.vk.com/method"
VK_API_VERSION = "5.199"
VK_WEBHOOK_PATH_PREFIX = "/api/vk_notify"
MAX_MESSAGE_LENGTH = 4000

EVENT_VK_NOTIFY_RECEIVED = "vk_notify_received"
