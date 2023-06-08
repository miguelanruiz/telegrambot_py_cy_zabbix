import sys, logging, io, re, os
from xml.dom import minidom
import platform
from typing import Any

NAME_PROGRAM_BOT = 'TelegramBot'

PATH_PID_FILE = '.'
PATH_CONFIG_FILE = '.'
PATH_LOG_FILE = '.'
PID_NAME = f'{NAME_PROGRAM_BOT.lower()}.pid'
if platform.system() == 'Linux':
    PATH_PID_FILE = f'/var/run/telegrambot/'
    PATH_CONFIG_FILE = '/etc/telegrambot/config.xml'
    PATH_LOG_FILE = f'/var/log/telegrambot/{NAME_PROGRAM_BOT.lower()}.log'
    try:
        os.mkdir('/var/log/telegrambot/')
        os.mkdir('/var/run/telegrambot/')
        os.mkdir('/etc/telegrambot/')
    except FileExistsError:
        pass
else:
    PATH_PID_FILE = os.getcwd()
    PATH_LOG_FILE = f'{NAME_PROGRAM_BOT.lower()}.log'
    PATH_CONFIG_FILE = './config.xml'
    with open(PATH_PID_FILE+PID_NAME, "w") as f:
        pass

USERS: Any = None
LOG_TYPE: Any = None 
LOGGER: Any = None
TOKEN = '1664021524:AAElacpxdP1DHSZWUGN3rrEahp1XKgVpF28'

def SETTINGS(ZabbixController: Any):
    global LOG_TYPE, TOKEN, USERS, LOGGER, PATH_LOG_FILE

    f = minidom.parse(PATH_CONFIG_FILE)
    inventory = f.getElementsByTagName('inventory')
    users = f.getElementsByTagName('user')
    log = f.getElementsByTagName('logFile')[0].firstChild.data
    sender = f.getElementsByTagName('sender')[0]
    tokens = f.getElementsByTagName('token')

    LOG_TYPE = getattr(logging, log)

    USERS = {}
    for user in users:
        user = user.firstChild.data.replace(',',' ').split()
        USERS[user[0]] = {
            'user': user[1], 
            'pass': user[2], 
            'server': user[3]
            }

    TOKEN = tokens[0].firstChild.data

    ZabbixController.EN_SENDER = eval(sender.childNodes[1].firstChild.data)
    ZabbixController.TELEGRAM_STATUS_SZ = sender.childNodes[3].firstChild.data
    ZabbixController.BOT_HOST_ZS = sender.childNodes[5].firstChild.data
    ZabbixController.ITEMS_KEYS = sender.childNodes[7].firstChild.data.replace(',',' ').split()
    ZabbixController.INVENTORY_FIELDS = inventory[0].firstChild.data.replace(',',' ').split()

    logging.basicConfig(level=LOG_TYPE,
                    filename=PATH_LOG_FILE,
                    filemode='w+',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    LOGGER = logging.getLogger('MODULE.'+__name__)
    LOGGER.setLevel(LOG_TYPE)
    ZabbixController.reloadItemsDiscovery()
    ZabbixController.autoDiscoveryItems()