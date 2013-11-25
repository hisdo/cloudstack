#!/usr/bin/python
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.





from ConfigParser import SafeConfigParser
from subprocess import *
from os import path
import time
import os

class StatusCodes:
    SUCCESS      = 0
    FAILED       = 1
    INVALID_INP  = 2
    RUNNING      = 3
    STOPPED      = 4
    STARTING     = 5

class Log:
    INFO = 'INFO'
    ALERT = 'ALERT'
    CRIT  = 'CRIT'
    NOTIF = 'NOTIF'

class Config:
    MONIT_AFTER_MINS = 30
    SLEEP_SEC = 1
    RETRY_ITERATIONS = 10
    RETRY_FOR_RESTART = 5
    MONITOR_LOG = '/var/log/monitor.log'
    UNMONIT_PS_FILE = '/etc/unmonit_psList.txt'


def getConfig( config_file_path = "/etc/monitor.conf" ):
    """
    Reads the process configuration from the config file.
    Config file contains the processes to be monitored.

    """
    process_dict = {}
    parser = SafeConfigParser()
    parser.read( config_file_path )


    for section in parser.sections():
        process_dict[section] = {}

        for name, value in parser.items(section):
            process_dict[section][name] = value
#           printd (" %s = %r" % (name, value))

    return  process_dict

def printd (msg):
    """
    prints the debug messages
    """

    #for debug
    #print msg
    return 0

    f= open(Config.MONITOR_LOG,'r+')
    f.seek(0, 2)
    f.write(str(msg)+"\n")
    f.close()

def raisealert(severity, msg, process_name=None):
    """ Writes the alert message"""

    #timeStr=str(time.ctime())
    if process_name is not None:
        log = '['+severity +']'+" " + '['+process_name+']' + " " + msg +"\n"
    else:
        log = '['+severity+']' + " " + msg +"\n"

    msg = 'logger -t monit '+ log
    pout = Popen(msg, shell=True, stdout=PIPE)


def isPidMatchPidFile(pidfile, pids):
    """ Compares the running process pid with the pid in pid file.
        If a process with multiple pids then it matches with pid file
    """

    if pids is None or isinstance(pids,list) != True or len(pids) == 0:
        printd ("Invalid Arguments")
        return StatusCodes.FAILED
    if not path.isfile(pidfile):
        #It seems there is no pid file for this service
        printd("The pid file "+pidfile+" is not there for this process")
        return StatusCodes.FAILED

    fd=None
    try:
        fd = open(pidfile,'r')
    except:
        printd("pid file: "+ pidfile +" open failed")
        return StatusCodes.FAILED


    inp = fd.read()

    if not inp:
        fd.close()
        return StatusCodes.FAILED

    printd("file content "+str(inp))
    printd(pids)
    tocheck_pid  =  inp.strip()
    for item in pids:
        if str(tocheck_pid) ==  item.strip():
            printd("pid file matched")
            fd.close()
            return StatusCodes.SUCCESS

    fd.close()
    return StatusCodes.FAILED



def checkProcessStatus( process ):
    """
    Check the process running status, if not running tries to restart
    """
    process_name = process.get('processname')
    service_name = process.get('servicename')
    pidfile = process.get('pidfile')
    #temp_out = None
    restartFailed=False
    pidFileMatched=False
    pids=''
    cmd=''
    if process_name is None:
        printd ("\n Invalid Process Name")
        return StatusCodes.INVALID_INP
    else:
        printd("checking the process " + process_name)
        cmd = 'pidof ' + process_name
        printd(cmd)
        #cmd = 'service ' + process_name + ' status'
        pout = Popen(cmd, shell=True, stdout=PIPE)
        exitStatus = pout.wait()
        temp_out = pout.communicate()[0]

    #check there is only one pid or not
    if exitStatus == 0:
        pids = temp_out.split(' ')
        msg="pids: " +temp_out;
        printd(msg)

        #there is more than one process so match the pid file
        #if not matched set pidFileMatched=False
        printd("Checking pid file")
        if isPidMatchPidFile(pidfile, pids) == StatusCodes.SUCCESS:
            pidFileMatched = True;
        else:
            pidFileMatched = False;

    if exitStatus == 0 and pidFileMatched == True:
        printd("The process is running ....")
        return  StatusCodes.RUNNING
    else:
        printd('exit status:'+str(exitStatus))
        msg="The process " + process_name +" is not running trying recover "
        printd(msg)
        #Retry the process state for few seconds
        for i in range(1, Config.RETRY_ITERATIONS):
            pout = Popen(cmd, shell=True, stdout=PIPE)
            exitStatus = pout.wait()
            temp_out = pout.communicate()[0]

            if i < Config.RETRY_FOR_RESTART: # this is just for trying few more times
                if exitStatus == 0:
                    pids = temp_out.split(' ')

                    if isPidMatchPidFile(pidfile, pids) == StatusCodes.SUCCESS:
                        pidFileMatched = True;
                        printd("pid file is matched ...")
                        raisealert(Log.ALERT, "The process detected as running", process_name)
                        break
                    else:
                        printd("pid file is not matched ...")
                        pidFileMatched = False;
                        time.sleep(Config.SLEEP_SEC)
                        continue
            else:
                msg="The process " +process_name+" is not running trying recover "
                raisealert(Log.INFO,process_name,msg)

                if service_name == 'apache2':
                    # Killing apache2 process with this the main service will not start
                    for pid in pids:
                        cmd = 'kill -9 '+pid;
                        printd(cmd)
                        Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT)

                cmd = 'service ' + service_name + ' restart'

                time.sleep(Config.SLEEP_SEC)
                #return_val= check_call(cmd , shell=True)

                cout = Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT)
                return_val = cout.wait()

                if return_val == 0:
                    printd("The process" + process_name +" recovered successfully ")
                    msg="The process " +process_name+" is recovered successfully "
                    raisealert(Log.INFO,msg,process_name)

                    break;
                else:
                    #retry restarting the process for few tries
                    printd("process restart failing trying again ....")
                    restartFailed=True
                    time.sleep(Config.SLEEP_SEC)
                    continue
        #for end here

        if restartFailed == True:
            msg="The process %s recover failed "%process_name
            raisealert(Log.ALERT,process_name,msg)

            printd("Restart failed after number of retries")
            return StatusCodes.STOPPED

    return  StatusCodes.RUNNING


def monitProcess( processes_info ):
    """
    Monitors the processes which got from the config file
    """
    if len( processes_info ) == 0:
        printd("Invalid Input")
        return  StatusCodes.INVALID_INP

    dict_unmonit={}
    umonit_update={}

    if not path.isfile(Config.UNMONIT_PS_FILE):
        printd('Unmonit File not exist')
    else:
        #load the dictionary with unmonit process list
        dict_unmonit = loadPsFromUnMonitFile()

    #time for noting process down time
    csec = repr(time.time()).split('.')[0]

    unMonitPs=False

    for process,properties in processes_info.items():
        #skip the process it its time stamp less than Config.MONIT_AFTER_MINS
        printd ("checking the process %s \n" %process)

        if not is_emtpy(dict_unmonit):
            if dict_unmonit.has_key(process):
                ts = dict_unmonit[process]
                printd("Time difference=%s" %str(int(csec) - int(ts)))
                tmin = (int(csec) - int(ts) )/60

                if ( int(csec) - int(ts) )/60 < Config.MONIT_AFTER_MINS:
                    raisealert(Log.ALERT, "The %s get monitor after %s minutes " %(process, Config.MONIT_AFTER_MINS))
                    printd('process will be monitored after %s min' %(str(int(Config.MONIT_AFTER_MINS) - tmin)))
                    unMonitPs=True
                    continue

        if checkProcessStatus( properties) != StatusCodes.RUNNING:
            printd( "\n Process %s is not Running"%process)
            #add this process into unmonit list
            printd ("updating the process for unmonit %s\n" %process)
            umonit_update[process]=csec


    #if dict is not empty write to file else delete it
    if not is_emtpy(umonit_update):
        writePsListToUnmonitFile(umonit_update)
    else:
        if is_emtpy(umonit_update) and unMonitPs == False:
            #delete file it is there
            if path.isfile(Config.UNMONIT_PS_FILE):
                printd("Removing the file %s" %Config.UNMONIT_PS_FILE)
                os.remove(Config.UNMONIT_PS_FILE)



def loadPsFromUnMonitFile():

    dict_unmonit = {}

    try:
        fd = open(Config.UNMONIT_PS_FILE)
    except:
        printd("Failed to open file %s " %(Config.UNMONIT_PS_FILE))
        return StatusCodes.FAILED

    ps = fd.read()

    if not ps:
        printd("File %s content is empty " %Config.UNMONIT_PS_FILE)
        return StatusCodes.FAILED

    printd(ps)
    plist = ps.split(',')
    plist.remove('')
    for i in plist:
        dict_unmonit[i.split(':')[0]] = i.split(':')[1]

    fd.close();

    return dict_unmonit;


def writePsListToUnmonitFile(umonit_update):
    printd("Write updated unmonit list to file")
    line=''
    for i in umonit_update:
        line+=str(i)+":"+str(umonit_update[i])+','
    printd(line)
    try:
        fd=open(Config.UNMONIT_PS_FILE,'w')
    except:
        printd("Failed to open file %s " %Config.UNMONIT_PS_FILE)
        return StatusCodes.FAILED

    fd.write(line);
    fd.close()


def is_emtpy(struct):
    """
    Checks wether the given struct is empty or not
    """
    if struct:
        return False
    else:
        return True

def main():
    '''
    Step1 : Get Config
    '''

    printd("monitoring started")
    temp_dict  = getConfig()


    '''
    Step2: Monitor and Raise Alert
    '''
    #raisealert(Log.INFO, 'Monit started')
    monitProcess( temp_dict )


if __name__ == "__main__":
    main()






