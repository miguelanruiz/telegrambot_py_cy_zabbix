import os
import sys
import threading
from libc.stdio cimport sprintf, printf
from posix.time cimport timeval, gettimeofday
from functools import wraps
from sender import ZabbixMetric

cdef char* C_KEY = "telegram.status[%s]";
cdef char* C_HOST = "Imagu-TelegramBot";

cdef char* HTTP_KEY = "HTTP"
cdef char* ZABBIX_KEY = "ZABBIX"  
#cdef char* BOT_KEY = "BOT"         #No implementado aun

ENCONDING: str = 'utf-8'

"""
Estructura para fururas implementaciones
"""
"""cdef struct c_metric:
    char*    host;
    char  key[30];
    timeval  time;
    double  value;
ctypedef c_metric z_metric;"""

CY_QUEUE: list = []

def getStart():
    """
    Metodo para obtener el valor de timestamp con formato float. 6 decimales.
    """
    cdef timeval timestamp;
    cdef double  time = 0.0;
    gettimeofday(&timestamp,NULL);
    time   = timestamp.tv_sec
    time  += <float> timestamp.tv_usec / 1000000.0
    return time


def http_decorator(func):
    """
    Este decorador creara una metrica a la funcion llamada, 
    haciendo uso de la clave en
    cdef char* C_KEY
    """
    @wraps(func)
    def _metric(*args, **kwargs):
        cdef timeval start;
        cdef timeval stop;

        cdef char  key[30];
        cdef double  value = 0.0;
        cdef double  time = 0.0;

        gettimeofday(&start,NULL);

        payload = func(*args, **kwargs)

        gettimeofday(&stop,NULL);
        
        sprintf(key,C_KEY,ZABBIX_KEY);
        value  = stop.tv_sec - start.tv_sec
        value += <float> (stop.tv_usec - start.tv_usec) / 1000000.0
        gettimeofday(&stop,NULL);
        time   = stop.tv_sec
        time  += <float> stop.tv_usec / 1000000.0
        CY_QUEUE.append(
            ZabbixMetric(
            host  = str(C_HOST, ENCONDING),
            key   = str(key, ENCONDING),
            value = value,
            clock = time
            )
        )
        return payload
    return _metric