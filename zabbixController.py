import unittest, sys, json, httpretty, argparse, datetime, traceback
import pandas as pd
import py_zabbix
import requests
import logging
from requests import Response
from sender import ZabbixMetric, ZabbixSender
from logging import NullHandler
from datetime import timedelta
from typing import Any
from py_zabbix import ZabbixAPI
import threading

null_handler = NullHandler()
logger = logging.getLogger('ZABBIX_CONTROLLER.'+__name__)
logger.addHandler(null_handler)

"""
Metodo de tiempo empaquetado en una variable.
"""
date = datetime.datetime

BOT_HOST_ZS = 'Imagu-TelegramBot'
TELEGRAM_STATUS_SZ = 'telegram.status[{}]'
TIMEOUT_SZ = 3

QUEUE_ZS: list = []
QUEUE_SM_ZS: list = []

"""
Las siguientes listas de claves, seran listadas a pesar de su reasignacion,
con motivo de tener presentes cuales son existentes y utilizables segun
el codigo escrito actualmente.
"""
ITEMS_KEYS = [
    "host",
    "graph" ,
    "trend" ,
    "history", 
    "inventory", 
    "problems",
    "availability_report",
    "top_100",
    "problems_general",
    "login"
    ]
ITEMS_ZABBIX = []

TELEGRAM_KEYS = [
    "login",
    "active_users",
    "activity",
    ]

ITEMS_TELEGRAM = []

ITEMS_ZABBIX = []
ITEMS_TELEGRAM = []
for key in ITEMS_KEYS:
    ITEMS_ZABBIX.append({'{#NAME}':key}) 
for key in TELEGRAM_KEYS:
    ITEMS_TELEGRAM.append({'{#NAME}':key}) 

def reloadItemsDiscovery():
    global ITEMS_ZABBIX, ITEMS_TELEGRAM
    ITEMS_ZABBIX = []
    ITEMS_TELEGRAM = []
    for key in ITEMS_KEYS:
        ITEMS_ZABBIX.append({'{#NAME}':key}) 
    for key in TELEGRAM_KEYS:
        ITEMS_TELEGRAM.append({'{#NAME}':key}) 

    """
    La reasignacion debe contener las siguientes metricas.
    """
    ITEMS_ZABBIX.append({'{#NAME}':'ZABBIX'})
    ITEMS_ZABBIX.append({'{#NAME}':'HTTP'})
    ITEMS_ZABBIX.append({'{#NAME}':'BOT'})

elementsToList = ['history','trend','trigger']

severities = {
    '0' : 'Not classified',
    '1' : 'Information',
    '2' : 'Warning',
    '3' : 'Average',
    '4' : 'High',
    '5' : 'Disaster'
}

SEVERI_EMOJIS = {
    '0' : '⚫',
    '1' : '🟣',
    '2' : '🟡',
    '3' : '⭕',
    '4' : '🟠',
    '5' : '🔴'
}

INVENTORY_FIELDS = [
    'name',
    'os',
    'location',
    'hw_arch',
    'location_lat',
    'location_lon',
    'poc_2_name',
    'notes'
    ]

"""
La variable sera llamada desde otro modulos,
para la asignacion a tiempo.
"""
METHOD: str = 'login'
EN_SENDER: bool = False

def autoDiscoveryItems():
    logger.debug('Running discovery items.') 
    ZABBIX_DISCOVERY = [
            ZabbixMetric(
                BOT_HOST_ZS, 
                'telegram[trapper]', 
                json.dumps(ITEMS_ZABBIX)
                ),
            ]
    TELEGRAM_DISCOVERY = [
            ZabbixMetric(
                BOT_HOST_ZS, 
                'telegram.user.util[trapper]', 
                json.dumps(ITEMS_TELEGRAM)
                ),
            ]
    sender = ZabbixSender(zabbix_server='54.167.133.204')
    print(sender.send(ZABBIX_DISCOVERY))
    print(sender.send(TELEGRAM_DISCOVERY))

def deliverCythonData():
    TEMP = py_zabbix.__get_list__()
    for chunk in TEMP:
        QUEUE_ZS.append(chunk)
        print(chunk.__repr__)
    py_zabbix.__set_list__()

def deliverCythonTime():
    return py_zabbix.__get_time__()

class ServerManager:

    def __init__(self,user=None,password=None,server=None):
        self.__server = server
        self.__passwd = password
        self.__user = user

    def __enter__(self):
        try:
            self.__datetime = date.now()
            self.zapi = ZabbixAPI(self.__server) 
            self.zapi.login(self.__user,self.__passwd)
            self.method = None
            logger.debug('User "%s" on "%s" succes login.', self.__user, self.__server) 
            return self
        except py_zabbix.ZabbixAPIException as e:
            if e.args[1] == -32602 or -32500:
                logger.warning('Invalid credentials or blocked user to log in on ZABBIX at SERVER: "%s", USER: "%s"',self.__server,self.__user)
                raise ValueError('Credenciales incorrectas o usuario temporalmente bloqueado, vuelva a intentarlo.',-1)
        except requests.exceptions.ConnectionError as e:
            traceback.print_exc()
            logger.error('Can not connect to server "%s",  TYPE: "%s" ,"%s".',self.__server,type(e), str(e))
            raise Exception('No se logro conectar el servidor.')
        except:
            traceback.print_exc()

    def getHostList(self, filterName = ''):
        try:
            addresses = dict()
            for hosts in self.zapi.host.get(output=['host','hostid'], search={'host':filterName}):
                addresses[hosts['hostid']] = hosts['host']
            return addresses
        except:
            traceback.print_exc()
            raise Exception('No se logro conseguir la lista.')
            #sys.exit()
    
    def getGroupHostList(self, filterName = ''):
        try:
            addresses = dict()
            for hosts in self.zapi.hostgroup.get(output=['name','groupid'], search={'name':filterName}):
                addresses[hosts['groupid']] = hosts['name']
            return addresses
        except Exception as e:
            traceback.print_exc()
            raise Exception("There is not a valid group."+str(e))
            #sys.exit()

    def getHostIdFromName(self,host):
        try:
            self.id = self.zapi.host.get(
                #output=['host','hostid'],
                filter={"host":host}
            )[0]['hostid']
        except:
            traceback.print_exc()
    
    def getDataCollection(self,schema,fromWhen,id,item_id: str = ''):
        '''
        En el API - event.get: Objectid  --> Hace referendia al triggerid
        '''
        try:
            if schema == elementsToList.index('trigger'):
                rawData = self.zapi.event.get(
                    output=['objectid','value','severity','name','acknowledged'],
                    filter={'value':'1'},
                    time_from=int(fromWhen),
                    sortfield='eventid',
                    sortorder='DESC',
                    selectHosts=['host']
                    )
                rawData = pd.DataFrame(data=rawData)
                # Agrupacion de datos y ordenarlos por conteo
                sortedData = rawData.groupby(['objectid']).count().sort_values(by=['eventid','severity'],ascending=False)
                # Extraer triggers ordenados del index
                triggers = sortedData.index.values.tolist()
                counter = sortedData['eventid'].values.tolist()
                payload = []
                try:
                    for element, count in zip(triggers, range(len(counter))):
                        issue = rawData.loc[rawData['objectid'] == element].values.tolist()[0]
                        counting = counter[count]
                        """TOP 100 MUST BE: SEVERITY_EMOJI Conteo HostName SEVERITY Name(Descripcion)"""
                        payload.append(SEVERI_EMOJIS[issue[3]]+' # '+str(counting)+' times '+issue[6][0]['host']+': '+issue[4])
                except:
                    traceback.print_exc()
                    pass
                return payload
            else: 
                item = self.zapi.item.get(
                    output=['units','key_','lastvalue','name'],
                    filter={"itemid":item_id}
                    )[0]
                trend = self.zapi.trend.get(
                    output=['value_min','value_avg','value_max','clock','sort'],
                    itemids=item_id,
                    time_from=int(fromWhen),
                    sortfield='clock',
                    sortorder='DESC'
                    )
                trend = trend.pop()
                unit = item['units']
                return 'Ultimo: {:.4f} {} \nProm:  {:.4f} {} \nMax:   {:.4f} {} \nMin:   {:.4f} {}'.format(float(item['lastvalue']),unit,float(trend['value_avg']),unit,float(trend['value_max']),unit,float(trend['value_min']),unit)
        except AttributeError:
            traceback.print_exc()
            return -1
        except IndexError:
            traceback.print_exc()
            raise KeyError("There is not data")
        except Exception:
            traceback.print_exc()

    def getImageFromId(self, credentials: dict):
        ssl_verify = True
        BASE_URL = credentials['server']

        payload = {
            'name': credentials['user'],
            'password': credentials['pass'],
            'enter': 'Sign in'
        }
        SESSION = requests.Session()
        SSL_VERIFY = ssl_verify

        # Construyendo el login y posteriormente el envio
        
        SESSION.post(f"{BASE_URL}/index.php",
                        data=payload,
                        verify=SSL_VERIFY)

        payload = bytearray()
        # Grafico tipo chart2.php
        with SESSION.get(
            f"{BASE_URL}/chart2.php?graphid={'1409'}&from={'now-1h'}&to={'now'}"+
            f"&profileIdx=web.graphs.filter&width={'700'}&height={'700'}",
            stream=True) as image:
            for chunk in image.iter_content(chunk_size=8192):
                payload += chunk
        return payload
  
    def getImageBehaivorFromId(self,
                        credentials: dict, 
                        item_ids: list,
                        from_date: str = "now-1d",
                        to_date: str = "now",
                        width: str = "1782",
                        height: str = "452",
                        batch: str = "1",
                        graph_type: str = "1",
                        output_path: str = None):
        global EN_SENDER
        ssl_verify = True
        BASE_URL = credentials['server']

        payload = {
            'name': credentials['user'],
            'password': credentials['pass'],
            'enter': 'Sign in'
        }
        SESSION = requests.Session()
        SSL_VERIFY = ssl_verify

         # Construyendo el login y posteriormente el envio
        
        SESSION.post(f"{BASE_URL}/index.php",
                        data=payload,
                        verify=SSL_VERIFY)

        encoded_itemids = "&".join(
            [f"itemids%5B{item_id}%5D={item_id}" for item_id in item_ids])
        # Grafico tipo chart.php
        payload = bytearray()
        start = py_zabbix.__get_time__()
        with SESSION.get(
                f"{BASE_URL}/chart.php?from={from_date}&to={to_date}&{encoded_itemids}"
                f"&type={graph_type}&batch={batch}&profileIdx=web.graphs.filter&width={width}&height={height}"
                f"",
                stream=True) as image:
            for chunk in image.iter_content(chunk_size=8192):
                payload += chunk
        stop = py_zabbix.__get_time__()
        if EN_SENDER:
            QUEUE_SM_ZS.append(
                ZabbixMetric(
                host  = BOT_HOST_ZS,
                key   = TELEGRAM_STATUS_SZ.format(NAME='HTTP'),
                value = stop - start,
                clock = stop
                )
            )
        return payload

    def getApplicationIds(self, hostid: str = None, application: str = 'TelegramKPI'):
        hosts = self.zapi.item.get(
            hostids=hostid, 
            tags=[{"tag": "Application" , "value": application, "operator": "0"}],
            output=['itemid','name','key_']
            )
        assert len(hosts) > 0 ,f'No hay items en la aplicacion {application} disponibles para visualizar'
        payload = []
        for item in hosts:
            payload.append(item)
        return payload

        """hosts = self.zapi.application.get(
            hostids=hostid,
            search={'name': application },
            selectItems=['itemid','name','key_']
            )
        assert len(hosts) > 0 ,f'No hay items en la aplicacion {application} disponibles para visualizar'
        payload = []
        for items in hosts:
            for item in items['items']:
                #Appending ['itemid','name','key_'] to list
                payload.append(item)
        return payload"""

    def getTypeItem(self, itemid):
        typeItem = self.zapi.item.get(
            itemids=itemid,
            output=['value_type']
            )
        return typeItem[0]['value_type']

    def getProblemsFor(self,hostid: str = None, period: str = ''):
        payload: list = []
        problems: Any = None
        """
        10771
        """
        problems = self.zapi.problem.get(
            hostids=hostid,
            output=['eventid','objectid','name','acknowledged','severity','clock'],
            #filter={'acknowledged':'0'},
            sortfield='eventid',
            sortorder='DESC',
            #time_from=int(period)
            )
        assert len(problems) > 0 ,'No hay datos para mostrar desde {}.'.format(datetime.datetime.fromtimestamp(int(period)).strftime('%Y-%m-%d %H:%M:%S')) 
        problems = pd.DataFrame(data=problems)
        keys = problems['objectid'].values.tolist()
        triggers = self.zapi.trigger.get(
            output=['triggerid','value','description','state','hosts'],
            triggerids=keys,
            selectHosts=['host'],
            preservekeys=True)
        try:
            for going in keys:
                issue = problems.loc[problems['objectid'] == going]
                issue = issue.values.tolist()[0]
                name = triggers[going]['hosts'][0]['host']
                clock_st = datetime.datetime.fromtimestamp(int(issue[5]))
                clock = clock_st.strftime('%Y-%m-%d %H:%M')
                """
                Syntax: eventid(problem_id), EVENT:SEVERITY, HOST:NAME, EVENT:NAME(description) 
                """
                payload.append([issue[0],f'{clock} {SEVERI_EMOJIS[issue[4]]}',name,issue[2]])
        except:
            traceback.print_exc()
        return payload

    def getHistoryFor(self,itemid: str = None, limit: int = 3):
        assert itemid is not None, 'Hubo un problema con la disponibilidad de este item.'
        item = self.zapi.item.get(
                itemids=itemid,
                output=['units','value_type'],
                #excludeSearch=True
            )
        units = item[0]['units']
        typeItem = item[0]['value_type']
        if len(units) == 0: units = ' NoUnits'
        payload: list = []
        data = self.zapi.history.get(
            history=typeItem,
            itemids=itemid,
            sortfield='clock',
            sortorder='DESC',
            limit=limit 
            )
        for item in data:
            time = datetime.datetime.fromtimestamp(int(item['clock']))
            time = time - timedelta(hours=5)
            time = time.strftime('%Y-%m-%d %H:%M:%S')
            payload.append('{} 🕖 {}{} '.format(time,item['value'],units))
        assert payload != [], f'No hay datos History para el item {itemid}'
        return payload

    def validateProblemId(self,problemid: str = ''):
        problem = self.zapi.problem.get(
                output=['eventid'],
                filter={'eventid': problemid }
            )
        return 1 if len(problem) > 0 else 0

    def setEventACK(self,problemid: str = None, message: str = None):
        assert problemid is not None, "Can't be empty problemid."
        assert message is not None, "Can't be empty message for {} item.".format(problemid)
        self.zapi.event.acknowledge(
            eventids=[problemid],
            action='6',
            message=message
            )    

    def setCloseEvent(self,problemid: str = None, message: str = None):
        assert problemid is not None, "Can't be empty problemid."
        assert message is not None, "Can't be empty message for {} item.".format(problemid)
        try:
            self.zapi.event.acknowledge(
                eventids=[problemid],
                action='5',
                message=message
                )   
        except:
            assert False, "No es posible cerrar este problema manualmente."

    def setEventMessage(self,problemid: str = None, message: str = None):
        assert problemid is not None, "Can't be empty problemid."
        assert message is not None, "Can't be empty message for {} item.".format(problemid)
        self.zapi.event.acknowledge(
                eventids=[problemid],
                action='4',
                message=message
            )

    def getInventoryFor(self, hostid: str = None):
        fromServer = self.zapi.host.get(
            hostids=hostid, 
            output=['hostid','host','inventory_mode','inventory'],
            selectInventory=INVENTORY_FIELDS, 
            searchInventory={'name':''},
            #filter={'inventory_mode':'1'},
            #excludeSearch=True,
            preservekeys=True)
        #print(len(fromServer))
        assert len(fromServer) > 0,'No hay datos para mostrar sobre estos hosts.'
        payload = {}
        for inventory in fromServer:
            host = fromServer[inventory]['inventory']
            dataHost = {}
            for e in INVENTORY_FIELDS:
                """Drop empty fileds from server"""
                if host[e] != '':
                    dataHost[e.replace('_',' ')] = host[e][:32].replace('_',' ')
                else:
                    continue
            """Drop empty var's"""
            if dataHost == []: continue
            payload[inventory] = dataHost
        assert len(payload.keys()) > 0 ,'No hay datos de inventario llenos para mostrar sobre estos hosts.'
        return payload
    """def getItemID(SUSPENDIDO)"""   
    def getItemID(self, element='', host_id: str = ''):
        try:
            if element == 'DISK':
                payload = self.zapi.item.get(
                    output=['units','key_','lastvalue','name'],
                    hostids=host_id,
                    search={"key_":"vfs.fs.size"},
                    #excludeSearch=True
                )
                return payload[0]['itemid']
            elif element == 'CPU':
                payload = self.zapi.item.get(
                    output=['units','key_','lastvalue','name'],
                    hostids=host_id,
                    search={"key_":"system.cpu.util"},
                    #excludeSearch=True
                )
                return payload[0]['itemid']
            elif element == 'MEMORY':
                payload = self.zapi.item.get(
                    output=['units','key_','lastvalue','name'],
                    hostids=host_id,
                    search={"key_":"vm.memory"},
                    #excludeSearch=True
                )
                return payload[0]['itemid']
            else:
                items = self.zapi.item.get(output=['units','key_','lastvalue','name'],
                    hostids=host_id,
                    search={"key_":"net.if.out"},
                    #excludeSearch=True
                    )
                items = pd.DataFrame(data=items)
                item = items.loc[items['lastvalue'] == items['lastvalue'].max()]
                item = item.values[0][0]
                del items
                return item
        except Exception as e:
            traceback.print_exc()

    def getAvailabilityReport(self, fromWhen='', hostid = '10084', period = 1598718242):
        """
        Parametrizacion del reporte a generar.
        """
        #clock_from = date.now() #DEBUG PURPOSE
        clock_from = int(period)
        clock_to = date.now()   #DEBUG PURPOSE
        clock_to = int(clock_to.timestamp())
        rawData = self.zapi.event.get(
            output=['eventid','objectid','clock','value','name'],
            hostids=hostid,
            #,filter={'value':'0'},
            selectHosts=['hostid','host'],
            time_from=clock_from,
            time_till=clock_to,
            sortfield='eventid',
            #,sortorder='DESC'
        )
        assistData: list = []
        rawData = pd.DataFrame(data=rawData)
        keys = rawData.groupby('objectid')[['eventid','objectid','clock','value']].groups.keys()
        keys = list(keys)
        rawData.groupby('objectid')[['eventid','objectid','clock','value','name','hosts']].apply(lambda x: assistData.append(self.calculateAvailability(x,clock_from,clock_to)))
        payload: dict = {}
        for val in keys:
            payload[val] = assistData[len(payload)]
        return payload
        
    def calculateAvailability(self,df: pd.DataFrame, fromTime, maxClock):
        """
        Metodologia basada en FrontEnd de ZABBIX:
        Dcoumentacion: 'https://git.zabbix.com/projects/ZBX/repos/zabbix/browse/ui/report2.php'
        Source: feature/ZBX-19102-5.0
        """
        #trigger = df['objectid'].head(1).values[0]
        time = fromTime
        false_time = 0
        true_time = 0
        """
        Implementacion basada en observacion a un unico Host.
        Extraer la Columna 'value' como int32 la posicion 1 y el valor de la lista 0
        (['16054', '16066', '17761']) --> Example.
        """
        state = 0
        for row in df.iterrows():   
            clock = int(row[1]['clock'])
            value = int(row[1]['value'])

            diff = max(clock - time,0)
            time = clock

            if state == 0:
                false_time += diff
                state = value
            
            elif state == 1:
                true_time += diff
                state = value
        #pivot = getter.trigger.get(output=['triggerid', 'value'],triggerids=[trigger])
        #state = int(pivot[0]['value'])
        if state == 0:
            false_time = false_time + maxClock - time
        elif state == 1:
            true_time = true_time + maxClock - time
        total_time = false_time + true_time
        """
        Formato de entrega de archivos.
        """
        payload = {
            'values' : [(false_time/total_time)*100,(true_time/total_time)*100],
            'host'   : df['hosts'].head(1).values[0][0]['host'],
            'name'   : df['name'].head(1).values[0]
        }
        return payload

    def __exit__(self,exception_type, exception_value, traceback):
        """
        Cierre de sesion para el usuario en ZABBIX.
        Al finalizar la transaccion, se evalua el ZABBIX_SENDER para encolamiento de metricas.
        """
        self.zapi.user.logout()

        if EN_SENDER and METHOD in ITEMS_KEYS:
            time = (date.now() - self.__datetime).total_seconds()
            print(threading.get_ident())
            QUEUE_ZS.append(
                ZabbixMetric(
                    host  = BOT_HOST_ZS, #'Imagu-TelegramBot' 
                    key   = TELEGRAM_STATUS_SZ.format(NAME=METHOD), 
                    value = time,
                    clock = date.now().timestamp()
                    )
                )

        self.__del__()

    def __del__(self):
        pass
        
