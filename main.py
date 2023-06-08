####################### IMAGUNET main.py TELEGRAMBOT #######################
#      Autor: Miguel Angel Ruiz
#      Fecha: 21/02/2021
#   Proyecto: TELEGRAMBOT
############################################################################
################## Bot de Telegram en ZABBIX: ##############################
#El Bot es un asistente de automatizacion de tareas mediante mensajes de texto o
#conversaciones de chat. Es utilizado en este programa, como un agente gestionador
#de transacciones de consulta y actualizacion en un servidor de ZABBIX para una
#determinada seleccion de clientes.
#Permite la descarga de graficos de comportamiento.
#La exploracion y visualizacion de datos desde el chat, que corresponden a informacion
#perteneciente a hosts.
#Actualizacion y cierre de problemas.
#Obtencion de alarmas TOP 100 y activas como problemas.
#############################################################################
import sys, json, argparse, unittest, logging, os, signal, traceback, pid, time, copy, schedule
from typing import Dict
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery, CallbackQuery, ForceReply, ChatAction, MessageEntity, ParseMode, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, Contact
import datetime
import zabbixController as zb
from datetime import timedelta
import io, re
from telegram import Message
from xml.dom import minidom
from pid import PidFile
import platform
from functools import wraps
import settings as s
from sender import ZabbixMetric, ZabbixSender
import threading

s.SETTINGS(zb)

from logging import NullHandler

null_handler = NullHandler()
logger = logging.getLogger('TELEGRAM_AGENT.'+__name__)
logger.addHandler(null_handler)

FILTER_HOST = 0
FILTER_HOST_GROUP = 1
FILTER_PERIOD = 2
FILTER_MENU = 3
PROBLEM_ACK_FINDING = 4 
PROBLEM_ACK_WRITING = 5
PROBLEM_ACK_SETTING = 6
PROBLEM_ACK_CHECKING = 7
PROBLEM_ACK_ASK_WRITE = 8
PROBLEM_ACK_MENU = 9
CHOOSING_PROBLEM = 10
CHOOSING_FEATURE = 11 
CHOOSING_TYPE = 12

GRANTED_USERS = s.USERS

REGEX_START_FILTER = re.compile(r'filtro', re.IGNORECASE)

STOP_CONV_INTERACTION = re.compile(r'listo', re.IGNORECASE) and re.compile(r'ya', re.IGNORECASE)

"""PROBLEMS_INTERPRETER_REPLY_TEXT = '''`
            ⚫ : Not classified
            🟣 : Information
            🟡 : Warning
            ⭕ : Average
            🟠 : High
            🔴 : Disaster`
            '''"""
PROBLEMS_INTERPRETER_REPLY_TEXT = '''`
            ⚫ : NotC
            🟣 : Info
            🟡 : Warn
            ⭕ : Avrg
            🟠 : High
            🔴 : Dist`
            '''

FILTER_PATTERN = {
    'HOST':'filter_host',
    'GROUP':'filter_group',
    'MENU_GENERAL':'filter_menu_general',
    'PERIOD':'filter_period',
    'MONITORING' : 'monitoring_menu',
    'TOOL' : 'monitoring_tool',
    'METHOD' : 'monitoring_method',
    'PROBLEM' : 'problem_ack_finding',
    'PROBLEM_ASK' : 'problem_ack_ask',
    'PROBLEM_SETTING' : 'problem_ack_setting',
    'PROBLEM_CHECK' : 'problem_ack_checking',
    'PROBLEM_MENU' : 'problem_ack_menu',
    'MENU_HOST_REQUEST': 'host_request_menu'
}

STATIC_PATTERN = {
    'FILTER_CONV' : 'private_filter_menu',
    'MENU_PROBLEM' : 'private_menu_problem',
    'MENU_MONITOR' : 'private_menu_monitor',
    'MENU_HOST': 'private_menu_j_host',
    'MENU_HOST_REQUEST': 'private_menu_host_r',
    'MENU_ACK': 'private_menu_trials',
}

"""globalCredentials = {
    '573194213279' : {'user': 'miguel.ruiz', 'pass': 'admin1', 'server': 'https://demo.imagunet.com/zabbix/'},
    #'573125165170' : {'user': 'Admin', 'pass': 'admin', 'server': 'http://localhost/zabbix'},
    '573125165170' : {'user': 'miguel.ruiz', 'pass': 'admin1', 'server': 'https://demo.imagunet.com/zabbix/'},
    '573054138136' : {'user': 'miguel.ruiz', 'pass': 'admin1', 'server': 'https://demo.imagunet.com/zabbix/'},
    '573023766597' : {'user': 'miguel.ruiz', 'pass': 'admin1', 'server': 'https://demo.imagunet.com/zabbix/'},
    '573045653587': {'user': 'miguel.ruiz', 'pass': 'admin1', 'server': 'https://demo.imagunet.com/zabbix/'}
}"""
"""
Listas de datos claves de los usuarios.
"""
ACTIVE_USERS: dict = {}
phonesIn: list = []
TELEGRAM_QUEUE_SZ: list = []


menuActions = {
    'Monitor' : 'Monitoring',
    #'Availability report': 'Availability',
    'Top 100 triggers': 'Top 100',
    'Problemas' : 'Problems'
}

subMenuMonitoring = {
    'Grafico' : 'GRAPH',
    'History' : 'HISTORY',
    'Ultimo trend' : 'LAST TREND',
    'Problemas' : 'PROBLEM',
    'Inventory' : 'INVENTORY',
    'Availability report' : 'AVAILABILITY',
    'Salir' : 'EXIT'
}

menuProblem = {
    'Cerrar Problema' : 'CLOSE',
    'Acknowledge' : 'ACK',
    'Mensaje' : 'MESSAGE',
    'Salir' : 'EXIT'
}

callback_menu_monitorig = """keyboard = []
for key in subMenuMonitoring:
    keyboard.append([InlineKeyboardButton(text=key, callback_data='{}{}'.format(FILTER_PATTERN['METHOD'],subMenuMonitoring[key]))])
reply_markup = InlineKeyboardMarkup(keyboard)
query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
query.message.reply_text(text="Por favor seleccione que desea obtener.",reply_markup=reply_markup)"""

callback_menu_general = """keyboard = []
for key in menuActions:
    keyboard.append([InlineKeyboardButton(text=key, callback_data='{}{}'.format(FILTER_PATTERN['MENU_GENERAL'],menuActions[key]))])
reply_markup = InlineKeyboardMarkup(keyboard)
query.message.reply_text(text=f'Bienvenido al menu principal.', reply_markup=reply_markup)"""

PERIODS = {
    '30 min': timedelta(minutes=30),
    '1 hora': timedelta(hours=1),
    '2 horas': timedelta(hours=2),
    '5 horas': timedelta(hours=5),
    '15 horas': timedelta(hours=15),
    '1 dia': timedelta(days=1),
    '7 dias': timedelta(days=7)
}

FILTER_MENU_MARKUP = [
    ['HOST', 'GROUP'],
    ['PERIOD'],
    ['Listo'],
]

TIMEOUT_CONVERSATION = 100
CALLS_TO_REPORT = 0

def scheduledSender():
    global CALLS_TO_REPORT, ACTIVE_USERS, TELEGRAM_QUEUE_SZ
    if zb.EN_SENDER:
        print("SENDING TO SERVER ACTIVE")
        zb.deliverCythonData()
        """
        Recepcion y reinicio de paquetes a transmitir.
        """
        ALL_PACKETS = zb.QUEUE_ZS       #CYTHON AND ITEMS
        SM_PACKETS = zb.QUEUE_SM_ZS
        TM_PACKETS = TELEGRAM_QUEUE_SZ

        zb.QUEUE_SM_ZS = []
        zb.QUEUE_ZS = []
        TELEGRAM_QUEUE_SZ = []

        """for packet in ALL_PACKETS:
            print(packet)"""

        ALL_PACKETS.append(
            ZabbixMetric(
                host  = 'Imagu-TelegramBot',
                key   = 'telegram.user.util[activity]', 
                value = CALLS_TO_REPORT,
                clock = getTimeUnix().timestamp()
                )
        )
        for packet in SM_PACKETS:
            ALL_PACKETS.append(packet)
        for packet in TM_PACKETS:
            ALL_PACKETS.append(packet)
        ALL_PACKETS.append(
            ZabbixMetric(
                host  = 'Imagu-TelegramBot',
                key   = 'telegram.user.util[active_users]', 
                value = len(ACTIVE_USERS),
                clock = getTimeUnix().timestamp()
                )
        )     
        """print("/////////////////////////////////////////")
        for packet in ALL_PACKETS:
            print(packet)"""
        #print(ALL_PACKETS)
        CALLS_TO_REPORT = 0
        SENDER = ZabbixSender(zabbix_server='54.167.133.204')
        print(ALL_PACKETS)
        print(SENDER.send(ALL_PACKETS))

def _report_thread():
    """
    Programacion del hilo encargado de transmitir las metricas a ZABBIX.
    """
    while True:
        if threading.active_count() < 3:
            break
        schedule.run_pending()
        time.sleep(1)

def _checkUserRecord(visitor: str = None):
    for user in ACTIVE_USERS:
        if ACTIVE_USERS[user]['phone'] == visitor:
            return True
    return False

def genInlineKeyboardMarkup(menu: dict = None, pattern = None, text= None, callback_data= None, yesno=False):
    keyboard = []
    """
    if yesno: 
        Teclado simple de solo patron
    elif c_d is None:
        Teclado comun de diccionarion en el texto del boton
    else:
        Teclado que especifica una clave para el texto y otra para el callback_data
    """
    if yesno:
        keyboard.append(
        [
            InlineKeyboardButton('Si', callback_data='{}{}'.format(pattern,'Si')),
            InlineKeyboardButton('No', callback_data='{}{}'.format(pattern,'No'))
            ]
        )
    elif callback_data is None:
        for key in menu:
                keyboard.append([InlineKeyboardButton(
                    text=key,
                    callback_data='{}{}'.format(pattern,menu[key])
                    )])
    else:
        for key in menu:
                keyboard.append([InlineKeyboardButton(
                    text=key[text],
                    callback_data='{}{}'.format(pattern,key[callback_data])
                    )])
    return InlineKeyboardMarkup(keyboard)

def assertItemsToFilter(items: list = None,update: Update = None, context: CallbackContext = None):
    """
    0: Priority group
    2: Handler on Dispatcher
    .states: States of ConvHandler
    """ 
    try:
        for item in items:
            assert context.user_data[item] != '*', f' Es necesario crear filto de {item} primero' 
        return False
    except AssertionError as e:
        """if is on MessageHandler else CallbackQueryHandler"""
        if hasattr(update.message,'__settext__'): 
            update.message.__settext__('filtro')
            context.dispatcher.handlers[0][2].handle_update(check_result=context.dispatcher.handlers[0][2].check_update(update),update=update,dispatcher=context.dispatcher)
            markup = ReplyKeyboardMarkup(FILTER_MENU_MARKUP, one_time_keyboard=True)
            update.message.reply_text(text=f'{str(e)} por favor aplicalo ahora.', reply_markup=markup)
        else:
            update.callback_query.__setdata__(STATIC_PATTERN['FILTER_CONV'])
            context.dispatcher.handlers[0][2].handle_update(check_result=context.dispatcher.handlers[0][2].check_update(update),update=update,dispatcher=context.dispatcher,context=context)
            markup = ReplyKeyboardMarkup(FILTER_MENU_MARKUP, one_time_keyboard=True)
            update.callback_query.message.reply_text(text=f'{str(e)} por favor aplicalo ahora.', reply_markup=markup)
        return True

def getTimeUnix():
    """
    Resumen:

    Funcion que captura el tiempo en el instante y lo retorna al llamar la funcion.
    @current_time[out] = Magnitud de tiempo, sin decimales.

    """
    current_time = datetime.datetime.now()
    return current_time

def _useSender(keys: list = None, data: list = None, custom = 'telegram.user.util[{NAME}]'):
    """
    Este debe usarse exclusivamente para encolar las metricas de TELEGRAM.
    """
    if zb.EN_SENDER:
        for key, chunk in zip(keys,data):
            if key in zb.TELEGRAM_KEYS:
                print(keys)
                print(data)
                print(custom.format(NAME=key))
                zb.QUEUE_ZS.append(
                    ZabbixMetric(
                        host  = 'Imagu-TelegramBot', 
                        key   = custom.format(NAME=key), 
                        value = chunk,
                        clock = getTimeUnix().timestamp()
                        )
                )

def _activityRecord(func):
    @wraps(func)
    def _make_report(*args, **kwargs):
        global CALLS_TO_REPORT, TELEGRAM_QUEUE_SZ
        CALLS_TO_REPORT += 1

        start = zb.deliverCythonTime()

        payload = func(*args, **kwargs)

        stop = zb.deliverCythonTime()

        TELEGRAM_QUEUE_SZ.append(
            ZabbixMetric(
            host  = zb.BOT_HOST_ZS,
            key   = zb.TELEGRAM_STATUS_SZ.format(NAME='BOT'),
            value = stop - start,
            clock = stop
            )
        )
        return payload
    return _make_report

def timeParserToText(fromDate: datetime.datetime , toDate: int = 1 ):
    """
    Este metodo retorna el tiempo en dias, de un diferencial
    entre un timestamp y un datetime. (timedelta)
    """
    until = datetime.datetime.fromtimestamp(toDate)
    instant = fromDate-until
    return round(instant.days*24+instant.seconds/3600)

def error_handler(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

@_activityRecord
def welcome_command(update: Update, context: CallbackContext) -> None:
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    reply_keyboard = [
        [KeyboardButton(text='Validar identidad',request_contact=True)]
    ]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    update.message.reply_text(text='Es necesario validar su identidad con el numero de telefono.', reply_markup=markup)
"""
def _send(func):
    #print(func.__name__)
    @wraps(func)
    def identifyCarrier(*args, **kwargs):
        print(func.__name__ + " was called from"+__name__)
        logger.debug('FUNCTION "%s" was called from "%s"', func.__name__, __name__)
        if isinstance(args[0], Update):     
            if hasattr(args[0].message,'__settext__'): 
                args[0].message.reply_text(text=f'Probando update is instance 0')
            else: 
                args[0].callback_query.message.reply_text(text=f'Probando isnt 0')
        else :
            if hasattr(args[1].message,'__settext__'): 
                args[1].message.reply_text(text=f'Probando update is instance 1')
            else: 
                args[1].callback_query.message.reply_text(text=f'Probando isnt 1')
        return func(*args, **kwargs)
    return identifyCarrier"""

@_activityRecord
def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    rawText = update.message.text
    """
    0: Priority group
    2: Handler on Dispatcher
    .states: States of ConvHandler
    """ 
    if text.find('menu') >= 0:
        reply_markup = genInlineKeyboardMarkup(menuActions, FILTER_PATTERN['MENU_GENERAL'])
        update.message.reply_text(text='Lista de herramientas disponibles. \nSelecciona una:', reply_markup=reply_markup)
    elif text.find('hola') >= 0:
        context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        update.message.reply_text(text='Hola {} bienvenido!\nPuedes pedirme el menu\
            \no validar tu identidad en /start'.format(update.message.from_user.first_name))

@_activityRecord
def callback_query_general(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    text = query.data.replace(FILTER_PATTERN['MENU_GENERAL'],'')
    command = text.lower()

    try:
        uuid = context.user_data['uuid']
        _user = ACTIVE_USERS[uuid]
        zb.METHOD = 'host'
        with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:

            if command.find('problems') >= 0:
                
                """
                Enter to ConvHandler
                """
                period = context.user_data['period']
                zb.METHOD = 'problems_general'
                problems = mgr.getProblemsFor(period=period)
                payload = '''*PROBLEMAS*'''
                payload += PROBLEMS_INTERPRETER_REPLY_TEXT
                for problem in problems:
                    if len(payload) + len(problem[0]) + len(problem[1]) + len(problem[2]) + len(problem[3]) <= 4096:
                        payload+= '''\n`ID '''+problem[0]+' '+problem[1]+' on '+problem[2]+': '+problem[3]+'''`'''
                    else: 
                        query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
                        payload = '''\n`ID '''+problem[0]+' '+problem[1]+' on '+problem[2]+': '+problem[3]+'''`'''
                payload += '''\n*Numero de eventos:* `'''+str(len(problems))+'''`'''
                query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
                update.callback_query.__setdata__(STATIC_PATTERN['MENU_PROBLEM'])
                context.dispatcher.handlers[0][4].handle_update(check_result=context.dispatcher.handlers[0][4].check_update(update),update=update,dispatcher=context.dispatcher,context=context)

            elif command.find('monitoring') >= 0:
                if assertItemsToFilter(['host'],update=update,context=context):
                    query.edit_message_text(text="*Confirme el filtro por favor*",parse_mode=ParseMode.MARKDOWN_V2)
                    return
                reply_markup = genInlineKeyboardMarkup(menu=subMenuMonitoring, pattern=FILTER_PATTERN['METHOD'])
                update.callback_query.message.reply_text(text="Por favor seleccione que desea obtener.",reply_markup=reply_markup)
                update.callback_query.__setdata__(STATIC_PATTERN['MENU_MONITOR'])
                context.dispatcher.handlers[0][3].handle_update(check_result=context.dispatcher.handlers[0][3].check_update(update),update=update,dispatcher=context.dispatcher,context=context)

            elif command.find('top 100') >= 0:
                lapse = context.user_data['period']
                zb.METHOD = 'top_100'
                msg = mgr.getDataCollection(2,fromWhen=lapse,id='None')
                payload = '''*TOP 100*'''
                payload += PROBLEMS_INTERPRETER_REPLY_TEXT
                for i in range(len(msg)):
                    if len(payload) <= 4096:
                        payload+= '''\n`'''+msg[i]+'''`'''
                    else: 
                        query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
                        payload = '''\n`'''+msg[i]+'''`'''
                payload += '''\n*Numero de eventos:* `'''+str(len(msg))+'''`'''
                query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
                exec(callback_menu_general)
            
            query.edit_message_text(text="*Ha seleccionado:* _{}_".format(text),parse_mode=ParseMode.MARKDOWN_V2)
    except KeyError as e:
        traceback.print_exc()
        if str(e) == "'uuid'":
            query.edit_message_text(text='Aun no ha validado identidad, ejecute /start para lograrlo.')
        elif str(e) == "'There is not data'" or str(e) == "'objectid'":
            query.edit_message_text(text=f'No hay aun datos disponibles en tu solititud.') 
        else: 
            query.edit_message_text(text=f'No ha completado los campos de {str(e)}') 
        pass
    except Exception as e:
        traceback.print_exc()
        query.edit_message_text(text=f'Se ha presentado un error de contexto: {str(e)}') 
        pass

@_activityRecord
def exchange_command(update: Update, context: CallbackContext):
    print(ACTIVE_USERS)
    update.message.reply_text(text=f'{context.user_data} and {phonesIn}')

@_activityRecord
def logout_command(update: Update, context: CallbackContext):
    update.message.reply_text(text=f'Gracias por usar nuestros servicios')
    identifier = context.user_data['uuid']
    del ACTIVE_USERS[identifier]
    del context.user_data['uuid']
    del context.user_data['host']
    del context.user_data['group']
    del context.user_data['period']
    del context.user_data['nested']

@_activityRecord
def filter_message_handler(update: Update, context: CallbackContext):
    if hasattr(update, 'message'):
        markup = ReplyKeyboardMarkup(FILTER_MENU_MARKUP, one_time_keyboard=True)
        update.message.reply_text(
            text='Iniciamos filtro, por favor escoge uno:',
            reply_markup=markup,
        )
    else:
        markup = ReplyKeyboardMarkup(FILTER_MENU_MARKUP, one_time_keyboard=True)
        update.callback_query.message.reply_text(
            text='Iniciamos filtro, por favor escoge uno:',
            reply_markup=markup,
        )
    return FILTER_MENU

@_activityRecord
def build_monitor_features(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    try:
        uuid = context.user_data['uuid']
        _user = ACTIVE_USERS[uuid]
        zb.METHOD = 'host'
        with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:
            host = context.user_data['host']
            menu = mgr.getApplicationIds(hostid=host)
            reply_markup = genInlineKeyboardMarkup(menu=menu, pattern=FILTER_PATTERN['MONITORING'], text='name', callback_data='itemid')
            update.message.reply_text(text='Seleccione que desea monitorear: ', reply_markup=reply_markup)
    except Exception as e:
        traceback.print_exc()
        update.message.reply_text(text=f'Problema con: {str(e)}')
        pass

@_activityRecord
def build_monitor_type(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    try:
        reply_markup = genInlineKeyboardMarkup(menu=subMenuMonitoring, pattern=FILTER_PATTERN['METHOD'])
        update.message.reply_text(text="Por favor seleccione que desea obtener.",reply_markup=reply_markup)
    except Exception as e:
        traceback.print_exc()
        update.message.reply_text(text=f'Problema con: {str(e)}')
        pass

@_activityRecord
def build_filter_host(update: Update, context: CallbackContext):
    """
    Filter based on text. When message_handler is on.
    """
    text = update.message.text.lower()
    if text == 'x':
        text = ''
    try:
        uuid = context.user_data['uuid']
        _user = ACTIVE_USERS[uuid]
        zb.METHOD = 'host'
        with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:
            hosts = mgr.getHostList(text)
            if len(hosts) == 0:
                update.message.reply_text(text='No existe alguno con ese nombre.')
            else:
                keyboard = []
                for key in hosts:
                    keyboard.append([InlineKeyboardButton(hosts[key], callback_data='{}{}'.format(FILTER_PATTERN['HOST'],key))])
                reply_markup = InlineKeyboardMarkup(keyboard)
                update.message.reply_text(text='Lista de host disponibles. \nSeleccione uno:', reply_markup=reply_markup)
    except KeyError:
        update.message.reply_text(text='Aun no ha validado identidad, ejecute /start para lograrlo.')
    except Exception as e:
        traceback.print_exc()
        update.message.reply_text(text=f'Problema con: {str(e)}')
        pass

@_activityRecord
def build_filter_group(update: Update, context: CallbackContext):
    """
    Filter based on text. When message_handler is on.
    """
    text = update.message.text.lower()
    if text == 'x':
        text = ''
    try:
        uuid = context.user_data['uuid']
        _user = ACTIVE_USERS[uuid]
        zb.METHOD = 'host'
        with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:
            groups = mgr.getGroupHostList(text)
            if len(groups) == 0:
                update.message.reply_text(text='No existe alguno con ese nombre.')
            else:
                keyboard = []
                for key in groups:
                    keyboard.append([InlineKeyboardButton(groups[key], callback_data='{}{}'.format(FILTER_PATTERN['GROUP'],key))])
                reply_markup = InlineKeyboardMarkup(keyboard)
                update.message.reply_text(text='Lista de Grupos disponibles. \nSeleccione uno:', reply_markup=reply_markup)
    except KeyError:
        update.message.reply_text(text='Aun no ha validado identidad, ejecute /start para lograrlo.')
    except Exception as e:
        traceback.print_exc()
        update.message.reply_text(text=f'Problema con: {str(e)}')
        pass

@_activityRecord
def build_filter_period(update: Update, context: CallbackContext):
    """
    Filter based on text. When message_handler is on.
    """
    text = update.message.text.lower()
    try:
        if text == 'x':
            context.user_data['period'] = '1 hora'
            return FILTER_MENU
        else:
            keyboard = []
            for key in PERIODS:
                keyboard.append([InlineKeyboardButton(text=key, callback_data='{}{}'.format(FILTER_PATTERN['PERIOD'],key))])
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(text='Seleccione el tiempo: ', reply_markup=reply_markup)
    except KeyError:
        update.message.reply_text(text='Aun no ha validado identidad, ejecute /start para lograrlo.')
    except Exception as e:
        traceback.print_exc()
        update.message.reply_text(text=f'Problema con: {str(e)}')
        pass

@_activityRecord
def build_problem_ack_finding(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    rawText = update.message.text

    try:
        uuid = context.user_data['uuid']
        _user = ACTIVE_USERS[uuid]
        zb.METHOD = 'problems'
        with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:
            """Context var"""
            period = context.user_data['period']
            host = context.user_data['host'] 
            problems = mgr.getProblemsFor(hostid=host if context.user_data['nested'] else None,period=period)
            keyboard = []
            for problem in problems:
                keyboard.append([InlineKeyboardButton(problem[0], callback_data='{}{}'.format(FILTER_PATTERN['PROBLEM'],problem[0]))])
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(text='Lista IDs de problemas disponibles:\n', reply_markup=reply_markup)
    except Exception as e:
        traceback.print_exc()
        update.message.reply_text(text=f'Se presento un error en: {str(e)}')

@_activityRecord
def build_problem_ack_writing(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    rawText = update.message.text
    context.user_data['payload'] = rawText
    problem = context.user_data['problem'] 
    reply_markup = genInlineKeyboardMarkup(pattern=FILTER_PATTERN['PROBLEM_SETTING'], yesno=True)
    update.message.reply_text(text=f'Esta seguro que desea enviar "{text}" a: {problem}\n', reply_markup=reply_markup)
    return PROBLEM_ACK_SETTING

@_activityRecord
def callback_query_filter_host(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    command = query.data.replace(FILTER_PATTERN['HOST'],'')
    context.user_data['host'] = command
    markup = ReplyKeyboardMarkup(FILTER_MENU_MARKUP, one_time_keyboard=True)
    query.edit_message_text(text=f'*Ha seleccionado:* _FILTER HOST {command}_', parse_mode=ParseMode.MARKDOWN_V2)
    query.message.reply_text(
            'Hola, por favor escoge un filtro a aplicar.',
            reply_markup=markup,
    )
    return FILTER_MENU

@_activityRecord
def callback_query_filter_group(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    command = query.data.replace(FILTER_PATTERN['GROUP'],'')
    context.user_data['group'] = command
    markup = ReplyKeyboardMarkup(FILTER_MENU_MARKUP, one_time_keyboard=True)
    query.edit_message_text(text=f'*Ha seleccionado:* _FILTER GROUP {command}_', parse_mode=ParseMode.MARKDOWN_V2)
    query.message.reply_text(
            'Hola, por favor escoge un filtro a aplicar.',
            reply_markup=markup,
    )
    return FILTER_MENU

@_activityRecord
def callback_query_filter_period(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    command = query.data.replace(FILTER_PATTERN['PERIOD'],'')
    context.user_data['period'] = (getTimeUnix()-PERIODS[command]).timestamp()
    markup = ReplyKeyboardMarkup(FILTER_MENU_MARKUP, one_time_keyboard=True)
    query.edit_message_text(text=f'*Ha seleccionado:* _PERIOD {command}_', parse_mode=ParseMode.MARKDOWN_V2)
    query.message.reply_text(
            'Hola, por favor escoge un filtro a aplicar.',
            reply_markup=markup,
    )
    return FILTER_MENU

@_activityRecord
def callback_query_monitor_features(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    command = query.data.replace(FILTER_PATTERN['MONITORING'],'')
    item_name = ''
    for key in query.message['reply_markup']['inline_keyboard']:
        if key[0]['callback_data'].find(command) >= 0:
            item_name = key[0]['text']
            break
    item_name = re.sub('[^A-Za-z0-9]+', '', item_name)
    try:
        uuid = context.user_data['uuid']
        _user = ACTIVE_USERS[uuid]
        """Context var"""
        context.user_data['method'] = command
        periodData = context.user_data['period'] 
        host = context.user_data['host']
        task = context.user_data['do']
        feature = command
        query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
        """ToHere"""
        with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:
            if task.find("GRAPH") >= 0:
                day = threading.Lock()
                day.acquire()
                zb.METHOD = 'graph'
                """
                Realizar ajustes de texto PAI
                """
                item = feature
                until = timeParserToText(fromDate=getTimeUnix(), toDate=int(periodData))
                photo = io.BytesIO(mgr.getImageBehaivorFromId(credentials=_user, item_ids=[str(item)],from_date=f'now-{until}h'))
                query.message.reply_photo(photo=photo, caption=item_name)
                day.release()

            elif task.find("LAST TREND") >= 0 :
                item = feature
                zb.METHOD = 'trend'
                msg = mgr.getDataCollection(1,periodData,host,item_id=str(item))
                if msg == -1:
                    query.edit_message_text(text='Aun no ha iniciado sesion.')
                    raise KeyError('login')
                elif msg == []:
                    query.message.reply_text(text='No hay aun datos disponibles.')
                    return
                payload = '''*''' + item_name + '''*'''
                payload += '''\n`''' + msg + '''`'''
                query.message.reply_text(text=payload, parse_mode=ParseMode.MARKDOWN_V2)
            
            elif task.find("HISTORY") >= 0:
                item = feature
                zb.METHOD = 'history'
                data = mgr.getHistoryFor(itemid=item)
                payload = '''*Ultimos datos: ''' + item_name + ''' history*'''
                for e in data:
                    if len(payload) <= 4096:
                        payload+= f'''\n`{e}`'''
                    else: 
                        query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
                        payload= f'''\n`{e}`'''
                query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
            
            reply_markup = genInlineKeyboardMarkup(menu=subMenuMonitoring, pattern=FILTER_PATTERN['METHOD'])
            query.message.reply_text(text="Por favor seleccione que desea obtener.",reply_markup=reply_markup)
            return CHOOSING_TYPE
            
    except KeyError as e:
        if str(e) == "'uuid'":
            query.edit_message_text(text='Aun no ha validado identidad, ejecute /start para lograrlo.')
        elif str(e) == "'Not avilable'":
            query.edit_message_text(text='Este dato no se encuentra disponible para el host.')
        else: 
            query.edit_message_text(text=f'No ha completado los campos de {str(e)}') 
        return ConversationHandler.END
    except AssertionError as e:
        query.edit_message_text(text=f'{str(e)}') 
        return ConversationHandler.END
    except Exception as e:
        traceback.print_exc()
        query.message.reply_text(text="Lo sentimos, no se ha podido concluir con exito su solicitud.")
        return ConversationHandler.END

@_activityRecord
def callback_query_monitor_type(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    command = query.data.replace(FILTER_PATTERN['METHOD'],'')
    try:
        uuid = context.user_data['uuid']
        _user = ACTIVE_USERS[uuid]
        with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:
            """Context var"""
            context.user_data['method'] = command
            periodData = context.user_data['period'] 
            host = context.user_data['host']
            """ToHere"""
            if command.find("GRAPH") >= 0:
                """
                Realizar ajustes de texto PAI
                """
                zb.METHOD = 'graph'
                context.user_data['do'] = 'GRAPH'
                host = context.user_data['host']
                menu = mgr.getApplicationIds(hostid=host)
                reply_markup = genInlineKeyboardMarkup(menu=menu, pattern=FILTER_PATTERN['MONITORING'], text='name', callback_data='itemid')
                update.callback_query.message.reply_text(text='Seleccione que desea monitorear: ', reply_markup=reply_markup)
                query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
                return CHOOSING_FEATURE

            elif command.find("LAST TREND") >= 0 :
                zb.METHOD = 'trend'
                context.user_data['do'] = 'LAST TREND'
                host = context.user_data['host']
                menu = mgr.getApplicationIds(hostid=host)
                reply_markup = genInlineKeyboardMarkup(menu=menu, pattern=FILTER_PATTERN['MONITORING'], text='name', callback_data='itemid')
                update.callback_query.message.reply_text(text='Seleccione que desea monitorear: ', reply_markup=reply_markup)
                query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
                return CHOOSING_FEATURE
            
            elif command.find('HISTORY') >= 0:
                zb.METHOD = 'history'
                context.user_data['do'] = 'HISTORY'
                host = context.user_data['host']
                menu = mgr.getApplicationIds(hostid=host)
                reply_markup = genInlineKeyboardMarkup(menu=menu, pattern=FILTER_PATTERN['MONITORING'], text='name', callback_data='itemid')
                update.callback_query.message.reply_text(text='Seleccione que desea monitorear: ', reply_markup=reply_markup)
                query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
                return CHOOSING_FEATURE

            elif command.find('INVENTORY') >= 0:
                zb.METHOD = 'inventory'
                info = mgr.getInventoryFor(hostid=host)
                payload = '''*Inventory Info*'''
                for key in info:
                    data = info[key]
                    for e in data:
                        if len(payload) <= 4096:
                            payload+= f'''\n`{e}: {data[e]}`'''
                        else: 
                            query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
                            payload= f'''\n`{e}: {data[e]}`'''
                #payload += '''\n*Numero de eventos:* `'''+str(len(problems))+'''`'''
                query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)

            elif command.find('PROBLEM') >= 0:
                zb.METHOD = 'problems'
                problems = mgr.getProblemsFor(hostid=host,period=periodData)
                payload = '''*PROBLEMAS*'''
                payload += PROBLEMS_INTERPRETER_REPLY_TEXT
                for problem in problems:
                    if len(payload) + len(problem[0]) + len(problem[1]) + len(problem[2]) + len(problem[3]) <= 4096:
                        payload+= '''\n`ID '''+problem[0]+' '+problem[1]+': '+problem[3]+'''`'''
                    else: 
                        query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
                        payload = '''\n`ID '''+problem[0]+' '+problem[1]+': '+problem[3]+'''`'''
                payload += '''\n*Numero de eventos:* `'''+str(len(problems))+'''`'''
                query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
                context.user_data['nested'] = True
                update.callback_query.__setdata__(STATIC_PATTERN['MENU_PROBLEM'])
                context.dispatcher.handlers[0][4].handle_update(check_result=context.dispatcher.handlers[0][4].check_update(update),update=update,dispatcher=context.dispatcher,context=context)
                return CHOOSING_PROBLEM

            elif command.find('AVAILABILITY') >= 0:
                if assertItemsToFilter(['host'],update=update,context=context):
                    query.edit_message_text(text="*Confirme el filtro por favor*",parse_mode=ParseMode.MARKDOWN_V2)
                    return
                host_id = context.user_data['host']
                lapse = context.user_data['period']
                zb.METHOD = 'availability_report'
                msg = mgr.getAvailabilityReport(hostid=host_id,period=lapse)
                """
                Formato ID Values GOOD BAD Host Name
                """
                payload = '''*AVAILABILITY `  GOOD   BAD`*'''
                for key in msg:
                    if len(payload) <= 4096:
                        payload+= '''\n`'''+'💚{:.4f} ❤️{:.4f}'.format(msg[key]['values'][0],msg[key]['values'][1])+'''`'''
                        payload+= '''\n`'''+'{}'.format(msg[key]['name'])+'''`'''
                    else:
                        payload = payload.replace('.',',')
                        query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
                        payload = '''\n`'''+'💚{:.4f} ❤️{:.4f}'.format(msg[key]['values'][0],msg[key]['values'][1])+'''`'''
                        payload+= '''\n`'''+'{}'.format(msg[key]['name'])+'''`'''
                payload = payload.replace('.',',')
                query.message.reply_text(text=payload,parse_mode=ParseMode.MARKDOWN_V2)
            else: 
                query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
                context.user_data['nested'] = False
                exec(callback_menu_general)
                return ConversationHandler.END
        #query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
        exec(callback_menu_monitorig)
        #return ConversationHandler.END
    except KeyError as e:
        if str(e) == "'uuid'":
            query.edit_message_text(text='Aun no ha validado identidad, ejecute /start para lograrlo.')
        elif str(e) == "'Not avilable'":
            query.edit_message_text(text='Este dato no se encuentra disponible para el host.')
        else: 
            query.edit_message_text(text=f'No ha completado los campos de {str(e)}') 
        reply_markup = genInlineKeyboardMarkup(menu=subMenuMonitoring, pattern=FILTER_PATTERN['METHOD'])
        query.message.reply_text(text="Por favor seleccione que desea obtener.",reply_markup=reply_markup)
    except AssertionError as e:
        query.edit_message_text(text=f'{str(e)}') 
        reply_markup = genInlineKeyboardMarkup(menu=subMenuMonitoring, pattern=FILTER_PATTERN['METHOD'])
        query.message.reply_text(text="Por favor seleccione que desea obtener.",reply_markup=reply_markup)
        return CHOOSING_TYPE
    except Exception as e:
        traceback.print_exc()
        query.message.reply_text(text="Lo sentimos, no se ha podido concluir con exito su solicitud.")
        return ConversationHandler.END

@_activityRecord
def callback_query_problem_ack_finding(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    command = query.data.replace(FILTER_PATTERN['PROBLEM'],'')
    context.user_data['problem'] = command
    query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
    reply_markup = genInlineKeyboardMarkup(menuProblem, FILTER_PATTERN['PROBLEM_MENU'])
    query.message.reply_text(text="Seleccione que dese hacer:",reply_markup=reply_markup)
    return PROBLEM_ACK_MENU

@_activityRecord
def callback_query_problem_ack_menu(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    command = query.data.replace(FILTER_PATTERN['PROBLEM_MENU'],'')
    query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
    if command.find('ACK') >= 0:
        reply_markup = genInlineKeyboardMarkup(pattern=FILTER_PATTERN['PROBLEM_CHECK'], yesno=True)
        query.message.reply_text(text="Por favor escriba el mensaje acompañante:")
        context.user_data['promise'] = True
        return PROBLEM_ACK_WRITING
    elif command.find('MESSAGE') >= 0:
        query.message.reply_text(text="Por favor escriba el mensaje a enviar:")
        context.user_data['promise'] = False
        return PROBLEM_ACK_WRITING
    elif command.find('CLOSE') >= 0:
        query.message.reply_text(text="Por favor escriba de cierre:")
        context.user_data['promise'] = 'C'
        return PROBLEM_ACK_WRITING
    else:
        if context.user_data['nested']:
            reply_markup = genInlineKeyboardMarkup(menu=subMenuMonitoring, pattern=FILTER_PATTERN['METHOD'])
            update.callback_query.message.reply_text(text="Por favor seleccione que desea obtener.",reply_markup=reply_markup)
            return CHOOSING_TYPE
        context.user_data['nested'] = False
        exec(callback_menu_general)
        return ConversationHandler.END

@_activityRecord
def callback_query_problem_ack_setting(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    command = query.data.replace(FILTER_PATTERN['PROBLEM_SETTING'],'')
    query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
    try:
        if command.find('Si') >= 0:
            uuid = context.user_data['uuid']
            _user = ACTIVE_USERS[uuid]
            phone = _user['phone']
            zb.METHOD = 'problems_general'
            if context.user_data['nested']:
                zb.METHOD = 'problems'
            problem = context.user_data['problem'] 
            with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:
                if context.user_data['promise'] == 'C':
                    mgr.setCloseEvent(problemid=problem,message='{PHONE} said {TEXT}'.format(PHONE=phone, TEXT=context.user_data['payload']))
                elif context.user_data['promise']:
                    mgr.setEventACK(problemid=problem,message='{PHONE} said {TEXT}'.format(PHONE=phone, TEXT=context.user_data['payload']))
                else:
                    mgr.setEventMessage(problemid=problem,message='{PHONE} said {TEXT}'.format(PHONE=phone, TEXT=context.user_data['payload']))
            del context.user_data['promise']
            del context.user_data['payload']
            query.message.reply_text(text="Envio exitoso.")
            reply_markup = genInlineKeyboardMarkup(menuProblem, FILTER_PATTERN['PROBLEM_MENU'])
            query.message.reply_text(text="Seleccione que dese hacer:",reply_markup=reply_markup)
            return PROBLEM_ACK_MENU
        else:
            reply_markup = genInlineKeyboardMarkup(menuProblem, FILTER_PATTERN['PROBLEM_MENU'])
            query.message.reply_text(text="Seleccione que dese hacer:",reply_markup=reply_markup)
            return PROBLEM_ACK_MENU
    except AssertionError as e:
        query.message.reply_text(text=str(e))
        reply_markup = genInlineKeyboardMarkup(menuProblem, FILTER_PATTERN['PROBLEM_MENU'])
        query.message.reply_text(text="Seleccione que dese hacer:",reply_markup=reply_markup)
        return PROBLEM_ACK_MENU

@_activityRecord
def callback_query_problem_ack_checking(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    command = query.data.replace(FILTER_PATTERN['PROBLEM_CHECK'],'')
    query.edit_message_text(text="*Ha seleccionado:* _{}_".format(command),parse_mode=ParseMode.MARKDOWN_V2)
    if command.find('Si') >= 0:
        uuid = context.user_data['uuid']
        _user = ACTIVE_USERS[uuid]
        """zb.METHOD = 'problems_general'
        if context.user_data['nested']:
            zb.METHOD = 'problems'"""
        """problem = context.user_data['problem'] 
        with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:
            mgr.setEventACK(problemid=problem)
        query.message.reply_text(text="ACK exitoso.")"""
        """reply_markup = genInlineKeyboardMarkup(menuProblem, FILTER_PATTERN['PROBLEM_MENU'])
        query.message.reply_text(text="Seleccione que dese hacer:",reply_markup=reply_markup)"""
        query.message.reply_text(text="Por favor escriba el mensaje acompañante:")
        return PROBLEM_ACK_WRITING
    else:
        reply_markup = genInlineKeyboardMarkup(menuProblem, FILTER_PATTERN['PROBLEM_MENU'])
        query.message.reply_text(text="Seleccione que dese hacer:",reply_markup=reply_markup)
        return PROBLEM_ACK_MENU

@_activityRecord
def conv_menu_filter(update: Update, context: CallbackContext):
    command = update.message.text.lower()
    markup = ReplyKeyboardMarkup(FILTER_MENU_MARKUP, one_time_keyboard=True)
    payload = ''
    if command.find('host') >= 0:
        payload = FILTER_HOST
    elif command.find('group') >= 0:
        payload = FILTER_HOST_GROUP
    elif command.find('period') >= 0:
        keyboard = []
        for key in PERIODS:
            keyboard.append([InlineKeyboardButton(text=key, callback_data='{}{}'.format(FILTER_PATTERN['PERIOD'],key))])
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(text='Seleccione el tiempo: ', reply_markup=reply_markup)
        return FILTER_PERIOD
    elif command.find('listo') >= 0:
        filter_menu_quit(update, context)
        return ConversationHandler.END
    else:
        update.message.reply_text(
            'Hola, por favor escoge un filtro a aplicar.',
            reply_markup=markup,
        )
        return FILTER_MENU
    update.message.reply_text(
        text="*Ha seleccionado:* _{}_ \n Por favor indique: \n x: Para cualquiera\n O escriba parte del nombre".format(command)
        ,parse_mode=ParseMode.MARKDOWN_V2
    )
    return payload

@_activityRecord
def filter_menu_quit(update: Update, context: CallbackContext):
    update.message.reply_text(
        '_Filtros aplicados correctamente_',parse_mode= ParseMode.MARKDOWN_V2, reply_markup=ReplyKeyboardRemove()
    )
    context.user_data['nested'] = False
    userFromChat = update.message.from_user
    reply_markup = genInlineKeyboardMarkup(menuActions, FILTER_PATTERN['MENU_GENERAL'])
    update.message.reply_text(text=f'Bienvenido {userFromChat.first_name}.', reply_markup=reply_markup)
    return ConversationHandler.END

@_activityRecord
def handle_contact(update: Update, context: CallbackContext):
    zb.METHOD = 'login'
    start = getTimeUnix()
    contact: Contact = update.effective_message.contact
    user = update.message.from_user

    if contact['user_id'] != user['id']:
        logger.warning('Fake user with phone "%s" tried to log in', contact.phone_number)
        update.message.reply_text(
            text=f'Usted no es el usuario que dice ser.',
            reply_markup=ReplyKeyboardRemove()
        )
        return

    phone = contact.phone_number
    phone = phone.replace('+','')
    print(phone)

    user_name = update.message.from_user.first_name

    if phone in GRANTED_USERS:
        # Si el usuario ya inicio sesion, reinicia las variables
        if _checkUserRecord(phone):
            update.message.reply_text(text=f'Usted {user_name}, ya se encuentra logueado.',reply_markup=ReplyKeyboardRemove())
            logger.warning('Attempt to repeat login from "%s" at "%s".', phone, start.strftime("%m/%d/%Y, %H:%M:%S"))
        else:
            identifier = len(ACTIVE_USERS)
            ACTIVE_USERS[identifier] = GRANTED_USERS[phone]
            ACTIVE_USERS[identifier]['phone'] = phone
            phonesIn.append(f' {phone}')
            context.user_data['uuid'] = identifier
            logger.warning('Log in from "%s" at "%s" succesfully.', phone, start.strftime("%m/%d/%Y, %H:%M:%S"))
            update.message.reply_text(text=f'Bienvenido {user_name} a {s.NAME_PROGRAM_BOT}.',reply_markup=ReplyKeyboardRemove())
            _useSender(
                keys = ['login'],
                data = [1]
                )
        
        context.user_data['host'] = '*'
        context.user_data['group'] = '*'
        context.user_data['period'] = (getTimeUnix()-PERIODS['7 dias']).timestamp()
        context.user_data['nested'] = False

        # Se llama manualmente a la funcion, simulando que el usuario la llama
        update.message.__settext__('menu')
        context.dispatcher.handlers[0][5].handle_update(check_result=context.dispatcher.handlers[0][5].check_update(update),update=update,dispatcher=context.dispatcher,context=context)
    else:
        _useSender(
            keys = ['login'],
            data = [0]
            )
        logger.warning('User not allowed "%s" tried to log in at "%s".', phone, start.strftime("%m/%d/%Y, %H:%M:%S"))
        update.message.reply_text(
            text=f'Lamentablemente {user_name}, no tiene permitido acceder al servidor.',
            reply_markup=ReplyKeyboardRemove()
            )
    stop = (getTimeUnix() - start).total_seconds()
    #zb.dispatchItemValue(name='active_users',value=len(ACTIVE_USERS),telegram=True)
    _useSender(
        keys   = [zb.METHOD],
        data   = [stop],
        custom = 'telegram.status[{NAME}]'
    )

@_activityRecord
def static_callback_filter(update:Update,context:CallbackContext):
    return FILTER_MENU

@_activityRecord
def static_callback_problem_ack(update: Update, context: CallbackContext):
    query: CallbackQuery = update.callback_query
    text = update.callback_query.data.replace(STATIC_PATTERN['MENU_PROBLEM'],'')
    command = update.callback_query.data.replace(STATIC_PATTERN['MENU_PROBLEM'],'')
    command = command.lower()

    try:
        if command.find('si') >= 0:
            uuid = context.user_data['uuid']
            _user = ACTIVE_USERS[uuid]
            zb.METHOD = 'problem'
            with zb.ServerManager(user=_user['user'],password=_user['pass'],server=_user['server']) as mgr:
                """Context var"""
                period = context.user_data['period']
                host = context.user_data['host'] 
                problems = mgr.getProblemsFor(hostid=host if context.user_data['nested'] else None, period=period)
                keyboard = []
                for problem in problems:
                    keyboard.append([InlineKeyboardButton(problem[0], callback_data='{}{}'.format(FILTER_PATTERN['PROBLEM'],problem[0]))])
                reply_markup = InlineKeyboardMarkup(keyboard)
                query.message.reply_text(text='Lista IDs de problemas disponibles:\n', reply_markup=reply_markup)
                query.edit_message_text(text="*Ha seleccionado:* _{}_".format(text),parse_mode=ParseMode.MARKDOWN_V2)
            return PROBLEM_ACK_FINDING
        elif command.find('no') >= 0:
            query.edit_message_text(text="*Ha seleccionado:* _{}_".format(text),parse_mode=ParseMode.MARKDOWN_V2)
            if context.user_data['nested']:
                reply_markup = genInlineKeyboardMarkup(menu=subMenuMonitoring, pattern=FILTER_PATTERN['METHOD'])
                update.callback_query.message.reply_text(text="Por favor seleccione que desea obtener.",reply_markup=reply_markup)
                return CHOOSING_TYPE
            exec(callback_menu_general)
            return ConversationHandler.END
        else: 
            reply_markup = genInlineKeyboardMarkup(pattern=STATIC_PATTERN['MENU_PROBLEM'], yesno=True)
            query.message.reply_text(text='Desea hacer ACK o dar un mensaje?', reply_markup=reply_markup)
    except Exception as e:
        traceback.print_exc()
        query.message.reply_text(text=f'Se presento un error en: {str(e)}')
    #return PROBLEM_ACK_FINDING

@_activityRecord
def static_callback_monitor(update: Update, context: CallbackContext):
    return CHOOSING_TYPE

"""
Tiempo asignado para el cumplimiento de tareas
.do(TAREA)
TAREA       --> func
schedule    --> Modulo que comprende sched y time.
"""
schedule.every(60).seconds.do(scheduledSender)
schedule.every(24).hours.do(zb.autoDiscoveryItems)

if __name__ == '__main__':
    try:
        with PidFile(pidname=s.PID_NAME,piddir=s.PATH_PID_FILE):
            logger.debug('PID_PROCESS_STARTED "%s" on "%s"', s.NAME_PROGRAM_BOT.lower(), s.PATH_PID_FILE)
            
            updater = Updater(
                token=s.TOKEN,
                request_kwargs={'read_timeout': 20, 'connect_timeout': 7},
                use_context=True,
                )

            updater.dispatcher.add_handler(CommandHandler(['hola','help','start'], welcome_command))
            updater.dispatcher.add_handler(CommandHandler('logout', logout_command))

            filter_handler = ConversationHandler(
                entry_points=[
                    MessageHandler(Filters.regex(REGEX_START_FILTER), filter_message_handler),
                    CallbackQueryHandler(
                            callback=static_callback_filter, pattern= STATIC_PATTERN['FILTER_CONV']
                        )
                ],
                states={
                    FILTER_HOST: [
                        MessageHandler(
                            Filters.text & ~(Filters.command | Filters.regex(STOP_CONV_INTERACTION)), build_filter_host
                        ),
                        CallbackQueryHandler(
                            callback=callback_query_filter_host, pattern= FILTER_PATTERN['HOST']
                        ),
                    ],
                    FILTER_HOST_GROUP: [
                        MessageHandler(
                            Filters.text & ~(Filters.command | Filters.regex(STOP_CONV_INTERACTION)), build_filter_group
                        ),
                        CallbackQueryHandler(
                            callback=callback_query_filter_group, pattern= FILTER_PATTERN['GROUP']
                        ),
                    ],
                    FILTER_PERIOD: [
                        MessageHandler(
                            Filters.text & ~(Filters.command | Filters.regex(STOP_CONV_INTERACTION)), build_filter_period
                        ),
                        CallbackQueryHandler(
                            callback=callback_query_filter_period, pattern= FILTER_PATTERN['PERIOD']
                        ),
                    ],
                    FILTER_MENU: [
                        MessageHandler(
                            Filters.text & ~(Filters.regex(STOP_CONV_INTERACTION)), conv_menu_filter
                        )
                    ],
                },
                fallbacks=[MessageHandler(Filters.regex(STOP_CONV_INTERACTION), filter_menu_quit)],
                #conversation_timeout=TIMEOUT_CONVERSATION,
            )

            problem_ack_handler = ConversationHandler(
                entry_points=[CallbackQueryHandler(callback=static_callback_problem_ack, pattern= STATIC_PATTERN['MENU_PROBLEM'])],
                states={
                    PROBLEM_ACK_FINDING: [
                        MessageHandler(
                            Filters.text & ~(Filters.command | Filters.regex(STOP_CONV_INTERACTION)), build_problem_ack_finding
                        ),
                        CallbackQueryHandler(
                            callback=callback_query_problem_ack_finding, pattern= FILTER_PATTERN['PROBLEM']
                        ),
                    ],
                    PROBLEM_ACK_MENU: [
                        CallbackQueryHandler(
                            callback=callback_query_problem_ack_menu, pattern= FILTER_PATTERN['PROBLEM_MENU']
                        ),
                    ],
                    PROBLEM_ACK_WRITING: [
                        MessageHandler(
                            Filters.text & ~(Filters.command | Filters.regex(STOP_CONV_INTERACTION)), build_problem_ack_writing
                        ),
                    ],
                    PROBLEM_ACK_SETTING: [
                        CallbackQueryHandler(
                            callback=callback_query_problem_ack_setting, pattern= FILTER_PATTERN['PROBLEM_SETTING']
                        ),
                    ],
                    PROBLEM_ACK_CHECKING: [
                        CallbackQueryHandler(
                            callback=callback_query_problem_ack_checking, pattern= FILTER_PATTERN['PROBLEM_CHECK']
                        ),
                    ],
                },
                fallbacks=[MessageHandler(Filters.regex(STOP_CONV_INTERACTION), filter_menu_quit)],
                map_to_parent={
                    # After showing data return to top level menu
                    CHOOSING_TYPE: CHOOSING_TYPE,
                },
                #conversation_timeout=TIMEOUT_CONVERSATION,
            )

            monitor_handler = ConversationHandler(
                entry_points=[CallbackQueryHandler(callback=static_callback_monitor, pattern= STATIC_PATTERN['MENU_MONITOR'])],
                states={
                    CHOOSING_FEATURE: [
                        MessageHandler(
                            Filters.text & ~(Filters.command | Filters.regex(STOP_CONV_INTERACTION)), build_monitor_features
                        ),
                        CallbackQueryHandler(
                            callback=callback_query_monitor_features, pattern= FILTER_PATTERN['MONITORING']
                        ),
                    ],
                    CHOOSING_TYPE: [
                        MessageHandler(
                            Filters.text & ~(Filters.command | Filters.regex(STOP_CONV_INTERACTION)), build_monitor_type
                        ),
                        CallbackQueryHandler(
                            callback=callback_query_monitor_type, pattern= FILTER_PATTERN['METHOD']
                        ),
                    ],
                    CHOOSING_PROBLEM : [
                        problem_ack_handler
                        ]
                    ,
                },
                fallbacks=[MessageHandler(Filters.regex(STOP_CONV_INTERACTION), filter_menu_quit)],
                #conversation_timeout=TIMEOUT_CONVERSATION,
            )
            
            #updater.dispatcher.add_handler(CallbackQueryHandler(callback=callback_query_general, pattern= FILTER_PATTERN['MENU_GENERAL'])) 
            updater.dispatcher.add_handler(filter_handler)
            updater.dispatcher.add_handler(monitor_handler)
            updater.dispatcher.add_handler(problem_ack_handler)
            updater.dispatcher.add_error_handler(error_handler)
            
            updater.dispatcher.add_handler(MessageHandler(filters=Filters.text, callback=handle_message))
            updater.dispatcher.add_handler(MessageHandler(filters=Filters.contact, callback=handle_contact))
            updater.dispatcher.add_handler(CallbackQueryHandler(callback=callback_query_general, pattern= FILTER_PATTERN['MENU_GENERAL'])) 
            
            updater.dispatcher.run_async(_report_thread)
            updater.start_polling()
            logger.warning('"%s": Bot started.',s.NAME_PROGRAM_BOT)
            updater.idle()
    except pid.base.PidFileAlreadyRunningError:
        logger.debug('Process already running "%s" on "%s"', s.NAME_PROGRAM_BOT.lower(), s.PATH_PID_FILE)
        logger.warning('"%s": Bot already running.',s.NAME_PROGRAM_BOT)
    except Exception as e:
        logger.error('EXCEPTION "%s"', str(e))
        logger.error('Exiting inmediatly!')
        logger.error('Unhandled start process "%s" on "%s"', s.NAME_PROGRAM_BOT.lower(), s.PATH_PID_FILE)
        sys.exit(1)