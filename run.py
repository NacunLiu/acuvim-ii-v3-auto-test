# File: run.py
# Author: Hongjian Zhu
# Date: August 7, 2023
# Last Edit Date: Dec 14, 2023
# Description: This script is primarily designed to automate the test cases section 2, Modbus Communication, for Acuvim II v3.
# Prerequisite Modules: kasaPlug.py, pattern.py, ip_tracker.py, portFinder.py, bacnetTest.py, Reference.png
# Optional Modules: easySwitch.py, push.py
from collections import defaultdict
import os
import asyncio
from time import sleep
from pymodbus.client import ModbusSerialClient, AsyncModbusSerialClient, AsyncModbusTcpClient 
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.utilities import computeCRC
from pymodbus.constants import Endian
import webbrowser
import subprocess
from pattern import starter,fail, success, p1Fail, p2Fail, allPassed, p1Passed, p2Passed
import serial
import time,datetime
from ip_tracker import targetIp
from kasaPlug import KasaSmartPlug
from portFinder import serial_ports
from push import run
import logging, coloredlogs
from bacnetTest import Client
import multiprocessing
###########################################################
logger = logging.getLogger(__name__)
coloredlogs.install(level='INFO', logger=logger, fmt='%(asctime)s %(hostname)s %(levelname)s %(message)s')

"""
AccuenergyModbusRequest Class
This class contains customized command 0x6A
"""
class AccuenergyModbusRequest():
  def __init__(self, Port,Baudrate):
    self.address = 38144
    self.count = 16
    self.Port = Port
    self.BR = Baudrate
    self.reset_counter = bytearray([0x01, 0x6A, 0x95, 0x00, 0x00, 0x01, 0x02, 0x00, 0x00])
    self.reset_latency = bytearray([0x01, 0x6A, 0x95, 0x02, 0x00, 0x01, 0x02, 0x00, 0x00])
    
  def timeMker(self,timeIncrement:int,currentTime:list) -> list:
      return str(currentTime+datetime.timedelta(minutes = timeIncrement))
  
  #dataLogLoader function:
  # Input: stampCount -> number of record wanted, interval -> duration of time period
  # Usage: this function will change the meter clock every 4 sec to massively produce data log records
  def dataLogLoader(self,stampCount,interval):
    client = ModbusSerialClient (method='rtu', port=self.Port, baudrate=self.BR, parity='N', 
                      stopbits=1,bytesize= 8,timeout=1, unit=1)
    client.connect()
    currentDate = str(datetime.datetime.now())[:10]
    date_string = "{} 14:30:00".format(currentDate)
    baseTime = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    timeInterval = 0
    for ix in range(stampCount):
        timeInterval = ix*interval
        TimeStamp = []
        meterTime = self.timeMker(timeInterval,baseTime)
        TimeStamp = [int(meterTime[:4]),int(meterTime[5:7]),int(meterTime[8:10]),
                     int(meterTime[11:13]),int(meterTime[14:16]),int(meterTime[17:19])]
        SyncModbusWriteRegisters(client,4160,TimeStamp)
        logger.debug('writing time {}-{} {}:{}:{}'
                     .format(TimeStamp[1],TimeStamp[2],TimeStamp[3],TimeStamp[4],TimeStamp[5]))
        sleep(4)  
    client.close()
    logger.info('New clock stamp has generated successfully')
  
  # readCounter function 
  # Usage: this function will read reboot counter      
  def readCounter(self):
    client = ModbusSerialClient (method='rtu', port=self.Port, baudrate=self.BR, parity='N', 
                            stopbits=1,bytesize= 8,timeout=1, unit=1)
    client.connect()
    rr = client.read_holding_registers(self.address, 1, slave=1)
    logger.info('Meter has a normal reboot time of {}'.format(rr.registers))
    client.close()
    return rr.registers[0]
  
  # Reboot Latency Register function
  # This function will use 6A command to clear out latency register
  async def rebootLatency(self):
    crc = computeCRC(self.reset_latency)
    self.reset_latency += crc.to_bytes(2, byteorder='big')
    ser = serial.Serial(port=self.Port, baudrate=self.BR, timeout=1)
    ser.write(self.reset_latency)
    ser.close()
    logger.debug('Cleaning Latency Register')
  
  # rebootcounter function
  # This function will reset the reboot register 
  def rebootCounter(self,option):
    start = self.readCounter()
    crc = computeCRC(self.reset_counter)
    self.reset_counter += crc.to_bytes(2, byteorder='big')
    ser = serial.Serial(port=self.Port, baudrate=self.BR, timeout=1)
    ser.write(self.reset_counter)
    ser.close()
    logger.debug('Cleaning reboot counter')
    end = self.readCounter()
    if(end==0 and start !=0):
      logger.info("Reboot counter reset test passed")
      pass
    elif(end==0 and start == 0):
      pass
    else:
      logger.error("FAIL TO RESET REBOOT COUNTER")
      option.failCount += 1
      option.failTest.append('\nCounter Fail to reset')

###########################################
# Purpose:
# synchronous connect and write through modbus rtu, allow changing protocol 1 from Modbus to Bacnet; NO NEED TO REBOOT
def syncConnectWrite(Baudrate,Port,Address,Value,promptEnable:bool = False): 
  client = ModbusSerialClient (method='rtu', port=Port, baudrate=Baudrate, parity='N', 
                            stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  client.connect()
  if(promptEnable):
    logger.info('Sync Connection Status: {}'.format(client.connected))
  SyncModbusWriteRegisters(client,Address,Value)
  client.close()

############################################
# Purpose:
# synchronous write to target register
# inputs: ModbusSerialClient, destination address, and list of values
def SyncModbusWriteRegisters(client, Address, Value): 
  #write_registers(address: int, values: List[int] | int, slave: int = 0, **kwargs: Any) ModbusResponse #0x10
  builder = BinaryPayloadBuilder(byteorder=Endian.Big)
  for value in Value:
    assert(value<=65535 and value>=0),"Input overflow~"
    builder.add_16bit_uint(value)
  client.write_registers(Address, builder.to_registers(),slave=1)

########################################
# Purpose: Open the target Ip in a separated browser
# Each process will first acquire a lock to prevent racing condition by allowing one browser to open at a time
# Will terminate the browser after testing
def openBrowser(acuClass,lock):
  if(not acuClass):
    logger.error('NO ADDRESS ERROR')
    pass
  else:
    with lock:
      pingTest(acuClass,True)
    
# Purpose: Set up connection to meter through Modbus TCP, read IP through Modbus TCP and verify correctness
async def AsyncModbusTCP(acuClass, Host):
  logger.info('Modbus TCP Communication {} test in progress....'.format(Host))
  address = Host
  slaveId = await AsyncModbusCheckReadRegisters(acuClass,4145)
  client = AsyncModbusTcpClient(Host)
  await client.connect()
  try:
    data = await asyncReadRegisters(client, 259, 2, slaveId)#slave id == 1
    try:
      ip = ''
      for reading in data.registers:      
        ip_hex = format(int(reading),'02X')
        if(reading>255):
          ip += str(int(ip_hex[:2],16)) + '.'+ str(int(ip_hex[2:],16))+'.'
        else:
           ip += str(int('0x00',16)) + '.'+ str(int(ip_hex,16))+'.'
      AD = ip[:-1]
      assert(AD==address)
      logger.info('Complete Modbus TCP Test successfully')
    except AssertionError:
      acuClass.failTest.append('\nModbus TCP Test Fail')
      acuClass.failCount += 1
      logger.error('Error happened when comparing ip address')
    client.close()
  except Exception as e:
    acuClass.failTest.append('\nModbus TCP Test Fail')
    acuClass.failCount += 1
    logger.exception('Unable to connect through Modbus TCP {}'.format(e))

##########################################
async def asyncReadRegisters(client, Address:int, Size:int, Slave:int = 1):
  rr = await client.read_holding_registers(address=Address,count=Size, slave=Slave)
  return rr

# Check if the custom register has default value of 0
async def AsyncModbusCheckReadRegisters(acuClass,readAddress = 27136):

  client = AsyncModbusSerialClient (method='rtu', port=acuClass.COM, baudrate=acuClass.BR, parity='N', 
                            stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  RR = await asyncReadRegisters(client,readAddress,1)

  try:
    assert len(RR.registers) == 1
  
  except AssertionError as e:
    logger.warning(e)
    acuClass.failCount += 1
    acuClass.failTest.append(e)
  client.close()

  if(readAddress!=27136):
    return RR.registers[-1]

#########################################
# purpose: store ip address of the meter
async def asyncModbusCheckIp(acuClass, client):
    rr = await asyncReadRegisters(client,259,2)
    ip = ''
    try:
      assert rr.registers    
      for reading in rr.registers:
        ip_hex = format(int(reading),'02X')

        if(reading>255):
          ip += str(int(ip_hex[:2],16)) + '.'+ str(int(ip_hex[2:],16))+'.'
        else:
           ip += str(int('0x00',16)) + '.'+ str(int(ip_hex,16))+'.'
      acuClass.address = ip[:-1]
      logger.info('{} ip address is: {}'.format(acuClass.serialNum, acuClass.address))

    except AttributeError:
       logger.error('Bad Connection, read ip address failed')
       
#######################################################################
# Purpose:
# This function will read the ip register through modbus, print out ip address
def modbusCheckIp(client):
    rr = client.read_holding_registers(address=259,count=2, slave=1) #address for channel 1 ip register with default slave id 1
    ip = ''
    try:
      assert rr.registers    
      for reading in rr.registers:
        ip_hex = format(int(reading),'02X')
        ip += str(int(ip_hex[:2],16)) + '.'+ str(int(ip_hex[2:],16))+'.'
      address = ip[:-1]
      logger.info('ip address is: {}'.format(address))
    except AttributeError:
       logger.error('Bad Connection, read ip address failed')

#######################################################################
# Purpose:
# recommended asynchronous connection through modbus rtu, avoid threads racing and lead to connection failure. 
async def asyncConnectIp(acuClass):
  client = AsyncModbusSerialClient (method='rtu', port=acuClass.COM, baudrate=acuClass.BR,\
    parity='N',stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  try:
    await client.connect()
    acuClass.plug.loading_animation(25)
    #logger.debug('Async Connection Status: {}'.format(client.connected))
    await asyncModbusCheckIp(acuClass, client)
    client.close()
  except Exception as e:
     acuClass.failCount += 1
     acuClass.failTest.append('\nasyncConnectIp function Failed{}'.format(acuClass.serialNum))
     logger.warning(e)
     logger.error("COM Occupied")
  await asyncio.sleep(10)
  

################################################################################
# Purpose: Modify IP address and disabled DHCP  /preset address: 192.168.63.202/or 63.201
# * subject to change if 
async def AsyncManualIpWrite(acuClass,Address=259,Value=[49320,16330]):
  logger.info('{} Manual DHCP Test in process.....'.format(acuClass.serialNum))
  await asyncConnectWrite(acuClass, 258, [0],'Disabling DHCP....') #set to DHCP Disabled
  await asyncio.sleep(5)
  if(acuClass.processNum ==1):
    await asyncConnectWrite(acuClass, Address, Value)
  elif(acuClass.processNum == 2):
    await asyncConnectWrite(acuClass, Address, [49320,16329]) #192.168.63.201
  await acuClass.plug.powerCycleSlow()
  await asyncConnectIp(acuClass)
  #REQUIRE POWERCYCLE

################################################################################
# Nothing diff to asyncConnectWrite function except an option to clear out all energy
async def asyncManualEnergyWrite(acuClass, Address, Values:list, Reset):
  if(Reset):
    await asyncConnectWrite(acuClass, 4118, [1])
    await asyncio.sleep(3)
  await asyncConnectWrite(acuClass, Address, Values)
  await asyncio.sleep(3)

#########################################
# Purpose: Generate some Energy readings
async def AsyncManualEnergyWriteLegacy(acuClass):
  logger.debug('Generating manual Energy in progress...')
  #Ep_imp, Ep_exp, Eq, Es, etc
  await asyncConnectWrite(acuClass,16456,[20,31679,0,21347,0,20528,1,57872,20,
                                          53026,20,10332,2,12865,65534,28193,21,62748])
  #Es_imp, Esa, Esb, phase-wise energy
  await asyncConnectWrite(acuClass,18688,[21,62748,7,18954,7,21871,7,21992,0,0,0,0,0,0,0,0])
  #Epa, Epb, phase-wise energy
  await asyncConnectWrite(acuClass,17952,[6,47101,0,6775,6,52223,0,12060,6,63425,0,
                                          2511,0,200,0,49436,0,11760,0,35876,0,5567,
                                          0,38094,7,18954,7,21871,7,21922])
  #four-quad energy q
  await asyncConnectWrite(acuClass,18704,[3,61059,0,835,0,1430,0,4828,0,35539,
                                          0,2365,0,10330,0,739,0,10944,0,13722,
                                          0,860,0,3081,3,39377,0,35713,0,35016,0,35013])
  #four-quad energy p
  #await asyncConnectWrite(Baudrate,Port,8328,[10,20497,0,23390,0,10333,8,28337,0,0,0,0,0,0,0,0,0,340,0,0,0,0,0,0,5,16296,0,0,5,12897,5,12897,14,45059,0,48296,0,17519,10,1549])
  #await asyncio.sleep(60) #wait until context is stored

async def asyncDHCPEnablePowerCycle(acuClass):
  await asyncConnectWrite(acuClass, 258, [1],'{} DHCP enabled'.format(acuClass.serialNum)) #Enabled DHCP 
  await acuClass.plug.powerCycleSlow()
  await asyncConnectIp(acuClass)


# Purpose: Enable DHCP
async def asyncDHCPEnable(acuClass):
  await asyncConnectWrite(acuClass, 258, [1],'{} DHCP enabled'.format(acuClass.serialNum)) #Enabled DHCP 
  
  #REQUIRE POWERCYCLE

# Purpose: Change Baudrate for channel 2
async def asyncChangeBaudrate2(acuClass,newBaudrate):
  await asyncio.sleep(8)
  await asyncConnectWrite(acuClass, 4143, [newBaudrate],'Changing baud rate on channel 2...')
  await asyncio.sleep(8)
  #REQUIRE POWERCYCLE

# Purpose: Change protocol for channel 2
async def asyncChangeProtocol2(acuClass, Mode=None, lock = None):
  await asyncio.sleep(5)
  if(Mode=='OTHER'):
    await asyncConnectWrite(acuClass, 4152, [0], '{} Changing channel 2 to Other'.format(acuClass.serialNum))
    await asyncChangeBaudrate2(acuClass,38400)
    await AsyncManualIpWrite(acuClass)
    sleep(15)
    openBrowser(acuClass, lock)
    await asyncDHCPEnablePowerCycle(acuClass)
    sleep(15)
    openBrowser(acuClass, lock)

  elif(Mode =='PROFIBUS'):
    MeterType = await meterModelScan(acuClass)
    if(MeterType != 'E'):
      await asyncConnectWrite(acuClass, 65280, [5], '{} Setting Profibus Id-> 5'
                              .format(acuClass.serialNum))
    else:
      logger.info('{} Default Profibus Id-> 2'.format(acuClass.serialNum))
    await asyncConnectWrite(acuClass, 4152, [5], '{} Changing channel 2 to Profibus'
                            .format(acuClass.serialNum))
  else:
    await asyncConnectWrite(acuClass, 4152, [4], 'Changing channel 2 to Web 2')
    asyncio.run(asyncChangeBaudrate2(acuClass,11520))
  #REQUIRE POWERCYCLE

## If possible, create an async version to prevent racing condition
def syncChangeBaudRate(acuClass):
  logger.info("{} Protocol 1 baud rate test in progress >>>".format(acuClass.serialNum))
  curRate = acuClass.BR
  dict = defaultdict(int)
  keys = [2400,4800,9600,19200,38400,57600,76800,115200]
  values = [2400,4800,9600,19200,38400,57600,7680,11520]
  for c,key in enumerate(keys):
    dict[key] = values[c]

  for rate in keys:
    syncConnectWrite(curRate, acuClass.COM ,4098,[dict[rate]])
    sleep(8)
    client = ModbusSerialClient(method='rtu', port=acuClass.COM, baudrate=rate, parity='N', 
                            stopbits=1,bytesize= 8,timeout=1, unit=1)
    client.connect()
    rr = client.read_holding_registers(address=4098,count=1, slave=1)
    assert(rr.registers[-1] == dict[rate])
    logger.info('{} baud rate {} passed'.format(acuClass.serialNum, rate))
    client.close()
    curRate = rate
  syncConnectWrite(curRate, acuClass.COM ,4098,[19200])
  
  # asyncFlagChecking: it will check the latency register 
  # Increment fail count if latency greater than 160, only trigger alert if greater than 140 
  
async def asyncFlagTest(acuClass):
  await asyncFlagChecking(acuClass,True)
  syncChangeBaudRate(acuClass)
  await asyncFlagChecking(acuClass,False)
  await AsyncModbusCheckReadRegisters
  
async def asyncFlagChecking(acuClass, resetEnable: bool):

  client = AsyncModbusSerialClient(method='rtu', port=acuClass.COM, baudrate=acuClass.BR, parity='N', 
                            stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  if(resetEnable):
    try:
      logger.debug('Erasing Latency Register....')
      newTest = AccuenergyModbusRequest(acuClass.COM,acuClass.BR)
      await newTest.rebootLatency()
      await client.connect()
      RR = await asyncReadRegisters(client,38146,1)
      latency = RR.registers[-1]
      logger.debug('Latency Register Reading: {}'.format(latency))
    except asyncio.exceptions.CancelledError as e:
      logger.warning('Flag check ERROR')
      
  else:
    await client.connect()
    RR = await asyncReadRegisters(client,38146,1)
    latency = RR.registers[-1]
    logger.debug('Latency Register Reading: {}'.format(latency))  
  client.close()

  if(latency>160):
    logger.warning("Alert! {} Latency is higher than {}".format(acuClass.serialNum, latency))
    acuClass.failCount += 1
    acuClass.failTest.append("Meter {} latency reaches {}".format(acuClass.serialNum, latency))
      
  elif(latency>140):
    logger.warning("Alert! {} Latency is {}".format(acuClass.serialNum,latency))

#This test is designed for non-display meter
#Currently not supported
async def NDModbusConfig(acuClass,round=0):
#round 1: Meter ought to be 9600-Modbus, examinate baudrate
  if(round==0):
    client = AsyncModbusSerialClient(method='rtu', port=acuClass.COM, baudrate=9600, parity='N', 
                        stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
    try:
      await client.connect()
      RR = await asyncReadRegisters(client,4098,1)
      client.close()
      logger.info('Meter @ Baud rate 9600 test passed, reading: {}'
                  .format(RR.registers[0]))
      #await asyncConnectWrite(19200,Port, 4094, [2])
      plug.loading_animation(60)
      
    except asyncio.exceptions.CancelledError:
      acuClass.failCount += 1
      logger.warning('Unable to connect at default 9600 for nd meter')
      
    await NDModbusConfig(acuClass,1)
    
  elif(round==1):
    try:
        client = AsyncModbusSerialClient(method='rtu', port=acuClass.COM, baudrate=19200, parity='N', 
                        stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
        await client.connect()
        RR = await asyncReadRegisters(client,4096,1)
    except asyncio.exceptions.CancelledError:
      logger.warning('Test passed')
      
    else:
      logger.warning('Test Failed, meter still in Modbus Mode')
      acuClass.failCount += 1
 
 # Purpose: This function will check the meter type (LCD or no LCD)
 # For LCD type, set channel 1 to BACnet with id of 4
 # *For non-LCD type, will perform NDModbus Test (currently not supported)
async def meterMountTypeScan(acuClass):
  client = AsyncModbusSerialClient(method='rtu', port=acuClass.COM, baudrate=acuClass.BR, parity='N', 
                            stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  RR = await asyncReadRegisters(client,61553,1)
  client.close()
  logger.info("{} MeterMountTest started".format(acuClass.serialNum))
  if(RR.registers[-1] == 0):
    #Set meter to BACnet with id=4
    logger.info("{} is set to BACnet id: 4".format(acuClass.serialNum))
    await asyncConnectWrite(acuClass,8449,[38400])
    await asyncConnectWrite(acuClass, 8451, [0,4])
    await asyncConnectWrite(acuClass,4094,[2])
  else:
    pass


# This function will read the meter model, will return a leter to indicate meter type
async def meterModelScan(acuClass) -> str: 

  MeterFamily = defaultdict(list)
  MeterFamily['A'] = ['CU0', 'CP0', 'CP2', 'CP4', 'CU2'] #Accuenergy model
  MeterFamily['E'] = ['CRD', 'CPG', 'CXD', 'CPD', 'CUG', 'CUD'] #Eaton model

  MeterFamily['D'] = ['CPB', 'CUB']
  
  client = AsyncModbusSerialClient(method='rtu', port=acuClass.COM, \
                                   baudrate=acuClass.BR, parity='N', 
                            stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  RR = await asyncReadRegisters(client,61440,2)
  Model = ''
  for reading in RR.registers:
    ascii_hex = format(int(reading),'02X')
    hex_bytes = bytes.fromhex(ascii_hex)
    Model += hex_bytes.decode('ascii')
  client.close()
  for key in MeterFamily:
    if(Model[:3] in MeterFamily[key]):
      return(key)

#Purpose: async read energy values
async def checkEnergy(acuClass,Address, Size):
  client = AsyncModbusSerialClient(method='rtu', port=acuClass.COM,\
                                    baudrate=acuClass.BR, parity='N', 
                          stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  RR = await asyncReadRegisters(client,Address,Size)
  client.close()
  return RR.registers
 
# New test should refer to checkEnergy function
async def checkEnergyLegacy(acuClass):  
  client = AsyncModbusSerialClient(method='rtu', port=acuClass.COM, \
                          baudrate=acuClass.BR, parity='N', 
                          stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  RR = await asyncReadRegisters(client,16456,18)
  RR2 = await asyncReadRegisters(client,18688,16)
  RR3 = await asyncReadRegisters(client,17952,30)
  Energy = RR.registers
  Energy += RR2.registers
  Energy += RR3.registers
  client.close()
  logger.debug('{} Energy: {}'.format(acuClass.serialNum,Energy))
  return Energy

##########################################
# Purpose: Async Connect and write to register
# recommended asynchronous connect and write through modbus rtu
async def asyncConnectWrite(acuClass, Address: int,\
  Value: list, prompt:str=None):
  if(prompt):
    logger.info(prompt)
  client = AsyncModbusSerialClient (method='rtu', \
    port= acuClass.COM, baudrate=acuClass.BR, parity='N', 
    stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  try:
    await client.connect()
    logger.debug('Async Connection Status: {}'.format(client.connected))
    await asyncModbusWriteRegisters(client,Address,Value)
  except Exception as e:
    acuClass.failCount += 1
    acuClass.failTest.append('\nCheck asyncConnectWrite function {} Value {}'
                             .format(acuClass.BR, Address))
    logger.exception("COM Port Occupied")
  await asyncio.sleep(3)
  client.close()
  
##########################################
# Purpose: Asyn write register
async def asyncModbusWriteRegisters(client, Address, Value: list): 
  #write_registers(address: int, values: List[int] | int, slave: int = 0, **kwargs: Any) ModbusResponse #0x10
  address = Address
  builder = BinaryPayloadBuilder(byteorder=Endian.Big)
  for value in Value:
    value = int(value)
    logger.debug('writing {} to {}'.format(value,address))
    address += 1
    assert(value<=65535 and value>=0),"Input Overflow~"
    builder.add_16bit_uint(value)
  await client.write_registers(Address, builder.to_registers(),slave=1)
    
##########################################
# pingTest:
# This module will ping the ip address three times. If error, prompt Error, otherwise, active
def pingTest(acuClass,open_browser=False):
  logger.info("{} Ping Test in process...".format(acuClass.serialNum))

  try:
      # Use subprocess to run the ping command
      result = subprocess.run(['ping', '-n', '5', acuClass.address], \
        capture_output=True, text=True, timeout=5)
      if result.returncode == 0:
          ping_status = "Network Active"
          if open_browser:
              webbrowser.open(acuClass.address)
              sleep(15)
              result = subprocess.run("taskkill /f /im msedge.exe"\
                                      , stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      else:
          ping_status = "{} Ping Test Failed, unable to communicate"\
            .format(acuClass.serialNum)
  except subprocess.TimeoutExpired:
      ping_status = "{} Ping Test Timed Out".format(acuClass.serialNum)
      acuClass.failCount += 1
      acuClass.failTest.append(ping_status)
      logger.error('{} Ping Test Timed Out'.format(acuClass.serialNum))
  except Exception as e:
      ping_status = f"Error: {str(e)}"
      acuClass.failCount += 1
      acuClass.failTest.append(ping_status)
      logger.error('Exception happend at ping test')

##########################################
# Compare energy readings with reference [contents]
async def ReadingComparator(acuClass,contents,start_address,size):
  Energy = await checkEnergy(acuClass,start_address,size)
  try:
    assert Energy == contents
    return True
  except AssertionError as e:
    logger.warning(e)
    return False

##########################################
# Purpose: verify if energy reading can be edit properly
async def energyLegitCheck(acuClass, SequenceId,Display,Control,MeterModel):
  DP_Type = defaultdict(str)
  DP_Type[0] = 'Primary 0.1'
  DP_Type[1] = 'Secondary 0.001'
  DP_Type[2] = 'Primary 0.001'
  # Eaton meter only support primary 0.1
  if(MeterModel == 'E' and (Display == 1 or Display == 2)): 
    return
  elif(not Control):
    pass
  else:
    logger.info('{} Change to Display Mode : {}'
                .format(acuClass.serialNum, DP_Type[Display]))
    await asyncConnectWrite(acuClass,4121,[Display])
  await asyncio.sleep(3)
  
  if(SequenceId == 1): 
    start_address = 16456
    contents = [15258,51711]*9
    await asyncManualEnergyWrite(acuClass, start_address, contents,True)
    await isMemorySectionEmpty(acuClass,start_address)
    if(await ReadingComparator(acuClass,contents,start_address,len(contents))):
      logger.info('{} Three-phase max Ep/q/s reading passed'
                  .format(acuClass.serialNum))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
    else:
      logger.error("Error for {} Three-phase max Ep/q/s reading test 1.1 @\
                    DP Mode {}".format(acuClass.serialNum, DP_Type[Display]))
      acuClass.failCount += 1
      acuClass.failTest.append("Error for {} Three-phase max Ep/q/s reading during\
                               test 1.1 Energy (1S) @ DP Mode {}"
                               .format(acuClass.serialNum, DP_Type[Display]))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
      
  elif(SequenceId == 2): #Energy (1S)
    start_address = 16456
    contents = [15258,51711]*5+[50277,13825]+[15258,51711]+[50277,13825]+[15258,51711]
    await asyncManualEnergyWrite(acuClass, start_address, contents,True)
    await isMemorySectionEmpty(acuClass,start_address)
    # await plug.powerCycleEnergy()
    if(await ReadingComparator(acuClass,contents,start_address,len(contents))):
      logger.info("{} Three-phase Negative Ep/q Test 1.2 passed"
                  .format(acuClass.serialNum))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
    else:
      logger.error("Error for {} three-phase Negative Ep/q during test 1.2 @ DP Mode {}"
                   .format(acuClass.serialNum, DP_Type[Display]))
      acuClass.failCount += 1
      acuClass.failTest.append("Error for {} Negative Ep/q during test 1.2 @ DP Mode {}"
                               .format(acuClass.serialNum, DP_Type[Display]))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
      
  elif(SequenceId == 3): # Energy -continue (1S)
    start_address = 17952
    contents = [15258,51711]*15
    await asyncManualEnergyWrite(acuClass, start_address, contents,True)
    await isMemorySectionEmpty(acuClass, start_address)
    if(await ReadingComparator(acuClass,contents,start_address,len(contents))):

      logger.info('{} Max Import/Export Ep/q/s Test passed'.format(acuClass.serialNum))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
    else:
      logger.error("Error for {} during Max Import/Export Ep/q Test @ DP Mode {}"
                   .format(acuClass.serialNum, DP_Type[Display]))
      acuClass.failCount += 1
      acuClass.failTest.append("Error for {} Max Import/Export Ep/q Test during Test 2 @ DP Mode {}"
                               .format(acuClass.serialNum, DP_Type[Display]))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
      
  elif(SequenceId == 4): #Import/Export Apparent Energy
    start_address = 18688
    contents = [15258,51711]*8
    await asyncManualEnergyWrite(acuClass, start_address, contents,True)
    await isMemorySectionEmpty(acuClass, start_address)
    if(await ReadingComparator(acuClass,contents,start_address,len(contents))):
      logger.info('{} Max Import/Export apparent energy Test 3 passed'
                  .format(acuClass.serialNum))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
    else:
      logger.error("Error for {} during Max Import/Export apparent energy Test 3 @ DP Mode {}"
                   .format(acuClass.serialNum, DP_Type[Display]))
      acuClass.failCount += 1
      acuClass.failTest.append("Error for {} during Max Import/Export apparent energy Test 3 @ DP Mode {}"
                               .format(acuClass.serialNum, DP_Type[Display]))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
      
  elif(SequenceId == 5): #Four-quadrant reactive energy
    start_address = 18704
    contents = [15258,51711]*16
    await asyncManualEnergyWrite(acuClass, start_address, contents,True)
    await isMemorySectionEmpty(acuClass, start_address)
    # await plug.powerCycleEnergy()
    if(await ReadingComparator(acuClass,contents,start_address,len(contents))):
      logger.info('{} Reactive 4-Q Test 4 passed'
                  .format(acuClass.serialNum))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
    else:
      logger.error("Error for {} during Reactive 4-Q @ DP Mode {}"
                   .format(acuClass.serialNum, DP_Type[Display]))
      acuClass.failCount += 1
      acuClass.failTest.append("Error for {} during Reactive 4-Q @ DP Mode {}"
                               .format(acuClass.serialNum, DP_Type[Display]))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
  
  elif(SequenceId == 6 and MeterModel in 'A'): #current meter will have problem in manual edit mode, subject to change based on meter release
    #TODO
    logger.info('Meter model: Accuenergy, Test 5 Skipped')
    await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
    
  elif(SequenceId == 6 and MeterModel in 'ED'):
    #TODO
    logger.info('Meter model: {} , Independant Energy related tests skipped'.format(MeterModel)) #Eaton/Deif meter does not support such feature
    await energyLegitCheck(acuClass, 9 ,Display,False,MeterModel)
  
  elif(SequenceId == 7): #Independent Input Channel Energy
    start_address = 9472
    contents = [15258,51711]*32
    await asyncManualEnergyWrite(acuClass, start_address, contents,True)
    await isMemorySectionEmpty(acuClass, start_address)
    if(await ReadingComparator(acuClass,contents,start_address,len(contents))):
      logger.info('{} 4Q Ep/q/s & channel 4 Max Energy Test 6a passed'.format(acuClass.serialNum))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
    else:
      logger.error("Error for {} during 4Q Ep/q/s & channel 4 Max energy Test 6a passed @ DP Mode {}"
                   .format(acuClass.serialNum, DP_Type[Display]))
      acuClass.failCount += 1
      acuClass.failTest.append("Error for {} during 4Q Ep/q/s & channel 4 Max energy Test 6a passed {}"
                               .format(acuClass.serialNum, DP_Type[Display]))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
      
  elif(SequenceId == 8): #Independent Input Channel Energy - Continued
    start_address = 9472
    contents = [15258,51711]*14+([50277,13825]+[15258,51711]*3)*2+[15258,51711]*12
    await asyncManualEnergyWrite(acuClass, start_address, contents,True)
    await isMemorySectionEmpty(acuClass, start_address)
    if(await ReadingComparator(acuClass,contents,start_address,len(contents))):
      logger.info('{} 4Q Ep/q/s & channel 4 Min Energy Test 6b passed'.format(acuClass.serialNum))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
    else:
      logger.error("Error for {} during 4Q Ep/q/s & channel 4 Min Energy Test 6b @ DP Mode {}"
                   .format(acuClass.serialNum, DP_Type[Display]))
      acuClass.failCount += 1
      acuClass.failTest.append("Error for {} during t4Q Ep/q/s & channel 4 Min Energy Test 6b @ DP Mode {}"
                               .format(acuClass.serialNum, DP_Type[Display]))
      await energyLegitCheck(acuClass, SequenceId+1,Display,False,MeterModel)
  
  elif(SequenceId == 9): # Verify if stored energy will remain after power-cycle
    await EnergyMemoryRetention(acuClass, False)
  return

# Purpose: Check if other energy reading regions are NULL
async def isMemorySectionEmpty(acuClass,StartAddress):
  client = AsyncModbusSerialClient (method='rtu', port=acuClass.COM, baudrate=acuClass.BR, parity='N', 
                          stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  MemoryAddress = defaultdict(int)
  MemoryAddress[16456] = 9
  MemoryAddress[17952] = 15
  MemoryAddress[18688] = 8
  MemoryAddress[18704] = 16
  MemoryAddress[9472] = 32
  for address,size in MemoryAddress.items():
    if(address!=StartAddress):
      Readings = await asyncReadRegisters(client,address,size)
      try:
        assert all(x==0 for x in Readings.registers)
      except AssertionError as e:
        acuClass.failCount+=1
        acuClass.failTest.append(e)
  logger.info('{} Unwritten Memory Section Check Passed'.format(acuClass.serialNum))  
  client.close()


async def AsyncReadModelType(Baudrate, COM):
  client = AsyncModbusSerialClient(method='rtu', port=COM, baudrate=Baudrate, parity='N', 
                        stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  RR = await asyncReadRegisters(client,61552,1)
  client.close()
  return RR.registers[-1]
  
# Energy memory retention test
# Purpose: 
async def EnergyMemoryRetention(acuClass, WaitControl):
  if(WaitControl):
    await asyncio.sleep(20)
  else:
    pass
  await AsyncManualEnergyWriteLegacy(acuClass)
  Energy = await checkEnergyLegacy(acuClass)
  try:
    assert Energy == [20,31679,0,21347,0,20528,1,57872,20,53026,20,10332,2,\
                      12865,65534,28193,21,62748,21,62748,7,18954,7,21871,
                      7,21992,0,0,0,0,0,0,0,0,6,47101,0,6775,6,52223,0,12060,\
                        6,63425,0,2511,0,3200,0,49436,0,11760,0,35876,
                      0,5567,0,38094,7,18954,7,21871,7,21922]
    await acuClass.plug.powerCycleSuperSlow()
    Energy = await checkEnergyLegacy(acuClass)
    assert Energy == [20,31679,0,21347,0,20528,1,57872,20,53026,20,10332,2,\
                      12865,65534,28193,21,62748,21,62748,7,18954,7,21871,
                      7,21992,0,0,0,0,0,0,0,0,6,47101,0,6775,6,52223,0,12060,\
                        6,63425,0,2511,0,3200,0,49436,0,11760,0,35876,
                      0,5567,0,38094,7,18954,7,21871,7,21922]
    logger.info('{} Memory retention test passed'.format(acuClass.serialNum))
    
  except AssertionError:
    acuClass.failCount += 1
    acuClass.failTest.append('\nEnergy memory retention test Fail')
    logger.error('{} Energy memory retention test has failed {}'.format(acuClass.serialNum, Energy))

# purpose: This function will clear all DI reading
async def asyncDIClear(acuClass):
  client = AsyncModbusSerialClient (method='rtu', port=acuClass.COM, baudrate=acuClass.BR, parity='N', 
                          stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  builder = BinaryPayloadBuilder(byteorder=Endian.Big)
  currentModel = input('Input DI Module (e.g. 11 represents AXM-IO11)')
  model = defaultdict(int)
  models = ['11','12','21','22','31','32']
  commands = [1,4,2,5,3,6]
  for index,Model in enumerate(models):
    model[Model] = commands[index]
  value = model[currentModel]
  logger.debug('writing {} to {}'.format(value,'Pulse clear'))
  builder.add_16bit_uint(value)
  await client.write_registers(4124, builder.to_registers(),slave=1)
  await asyncio.sleep(2)
  rr = await client.read_holding_registers(17225,count=56, slave=1)
  if(all(element == 0 for element in rr.registers)):
    pass
  else:
    failTest.append('\nError happened setting pulse registers to zero')
    failCount += 1
  await asyncio.sleep(2)
  client.close()

#this will reset to factory default 
async def AsyncFactoryDefault(Baudrate):
  global gCOM,failCount, failTest
  client = AsyncModbusSerialClient (method='rtu', port=gCOM, baudrate=Baudrate, parity='N',
                          stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  builder = BinaryPayloadBuilder(byteorder=Endian.Big)
  value = 1
  builder.add_16bit_uint(value)
  await client.write_registers(4134, builder.to_registers(),slave=1)
  client.close()

# Purpose: create a Client class (import from bacnetTest.py)
# Prerequisite: YABE installed, 
def BACnetConnectionTest(acuClass):
  BACnetClient = Client(acuClass.serialNum, acuClass.processNum)
  if(BACnetClient.run()):
    logger.info('{} BACnet Test Passed'.format(acuClass.serialNum))
  else:
    logger.warning('{} BACnet Test Failed'.format(acuClass.serialNum))
    acuClass.failCount += 1
    acuClass.failTest.append('\nBACnet Test Failed')

# Purpose: Async write register through TCP
async def asyncTCPWriteRegisters(client,address, Values,slaveId):
  start_address = address
  builder = BinaryPayloadBuilder(byteorder=Endian.Big)
  for value in Values:
    value = int(value)
    logger.debug('writing {} to {}'.format(value,address))
    address += 1
    assert(value<=65535 and value>=0),"Input Overflow~"
    builder.add_16bit_uint(value)
  await client.write_registers(start_address, builder.to_registers(),slave=slaveId)
  
#return the serial number string
async def AsyncReadSerialId(acuClass, slaveId):
  client =  AsyncModbusSerialClient (method='rtu', port=acuClass.COM, baudrate=acuClass.BR, parity='N', 
                            stopbits=1,bytesize= 8,timeout=1, framer=ModbusRtuFramer)
  await client.connect()
  try:
    SR = await client.read_holding_registers(61504,6, slaveId)
    SerialNumber = ''
    for reading in SR.registers:
      ascii_hex = format(int(reading),'02X')
      
      hex_bytes = bytes.fromhex(ascii_hex)
      SerialNumber += hex_bytes.decode('ascii')
      client.close()
    return SerialNumber[:-1]
  except Exception as e:
    acuClass.failCount += 1
    acuClass.failTest.append(acuClass.serialNum)
    client.close()
    return ''
  
# Main Class TestRunner for parallel testing
# Key inputs: processId, Com port, KasaPlug class, (Default baudrate: 19200)
class TestRunner:
  def __init__(self, pNum, plug, port):
    self.BR = 19200
    self.COM = port
    self.failTest = []
    self.failCount = 0
    self.plug = plug
    self.processNum = pNum
    self.serialNum = None
    self.logFile = None
    self.pid = None
    self.address = None
  
  # Purpose: generate a log file for each testing meter
  def wrapper(self,name=None):
    self.pid = os.getpid()
    try:
      SerialId = asyncio.run(AsyncReadSerialId(self, 1))
    except asyncio.exceptions.CancelledError:
      SerialId = 'acuTestlog'
    if(name):
      logFileName = SerialId+name+'.log'
    else:
      logFileName = SerialId+'.log'
    self.logFile = logging.FileHandler(logFileName,mode='w')
    self.logFile.setLevel(logging.DEBUG)
    logger.addHandler(self.logFile)
    self.serialNum = asyncio.run(AsyncReadSerialId(self,1))

  # Frame for Web WebPush Test
  def run_webpush(self,shared_failCount,lock,OpenYabeLock):
    self.wrapper('WebPush')
    logger.info('Process NO. {}, pid {}'.format(self.processNum, os.getpid()))
    asyncio.run(asyncChangeProtocol2(self,'OTHER', lock))
    #asyncio.run(AsyncManualIpWrite(self)) #set manual ip to 192.168.63.202 MODBUS ADD:258->0
    # logger.info('WEB Push Test in Process....')
    # asyncio.run(asyncConnectIp(self))
    # sleep(15)
    # openBrowser(self, lock)
    # sleep(15)
    # asyncio.run(asyncDHCPEnablePowerCycle(self)) #4+
    # sleep(30)
    #After webpush test, 
    asyncio.run(asyncChangeProtocol2(self,'PROFIBUS')) #change channel 2 to profibus
    logger.info('Protocol 1 is now set to BACnet, id of 3')

    asyncio.run(meterMountTypeScan(self)) #change channel 1 to BACnet
    with OpenYabeLock:
      BACnetConnectionTest(self)  
    if(self.failCount==0):
      print(success)
    else:
      with shared_failCount.get_lock():
        value = shared_failCount.value
        value += 1
        shared_failCount.value = value
      print(fail)
      parseError2 = ''
      for bugs in self.failTest:
        parseError2 += str(bugs) + ' '
      run('Meter {} Test fails, with {} Errors {}'\
        .format(self.serialNum,self.failCount,parseError2))
      logger.error("Fail {} tests: {}"\
        .format(self.failCount,parseError2))
      #logger.info('Test Failed {}'.format(parseError2))
      self.failTest.append(self.serialNum)
    logger.info('Phase 2 (Web push & BACnet) test completed')
    self.logFile.close()


  # main test framework, subject to add new tests/parameters
  # Inputs: shared_failCount -> global variable, need to acquire permit by calling share_failCount.get_lock()
  def run_tests(self, shared_failCount, lock):
    self.wrapper()
    logger.info('Process NO. {}, pid {}'.format(self.processNum, os.getpid()))
    # asyncio.run(asyncFlagTest(self))
    asyncio.run(asyncFlagChecking(self, True))
    syncChangeBaudRate(self)
    asyncio.run(asyncFlagChecking(self, False))
    asyncio.run(AsyncModbusCheckReadRegisters(self))
  
    #Energy reading remain after power cycle; Max/Min editing range test
    Model = asyncio.run(meterModelScan(self))
    if(Model == 'E'):
      asyncio.run(energyLegitCheck(self,1,0,True,Model)) 
    else:
      for i in range(3):
        asyncio.run(energyLegitCheck(self,1,i,True,Model))   
  
    logger.info('{} DHCP Disabled'.format(self.serialNum))
    asyncio.run(AsyncManualIpWrite(self)) #set manual ip to 192.168.63.202 MODBUS ADD:258->0
    #asyncio.run(self.plug.powerCycle(130)) # wait for 90 sec
    # asyncio.run(asyncConnectIp(self)) #Inquire Ip address from Modbus Register
    sleep(15)
    openBrowser(self, lock)

    logger.info("{} Static Ip Test on protocol 'Others' Finished".format(self.serialNum))
    asyncio.run(asyncDHCPEnablePowerCycle(self)) 
    # asyncio.run(self.plug.powerCycleSlow())
    # asyncio.run(asyncConnectIp(self))
    sleep(15)
    openBrowser(self, lock)

    logger.info("{} Finished DHCP Test on protocol 'Others'".format(self.serialNum))
    logger.info('Changing {} protocol 2 to WEB2 with baud rate of 115200'.format(self.serialNum))
    asyncio.run(asyncChangeProtocol2(self))
    # asyncio.run(asyncChangeBaudrate2(self,11520))
  
    #web2 fixed ip
    logger.info('{} DHCP disable'.format(self.serialNum))
    asyncio.run(AsyncManualIpWrite(self)) #set manual ip to 192.168.63.202/201 MODBUS ADD:258->0
    #asyncio.run(self.plug.powerCycle(130)) 
    asyncio.run(asyncConnectIp(self)) #Inquire Ip address from Modbus Register
    openBrowser(self, lock)    

    #web 2 dhcp
    asyncio.run(asyncDHCPEnable(self)) #4  
    asyncio.run(self.plug.powerCycleSlow())
    asyncio.run(asyncConnectIp(self))
    openBrowser(self, lock)    

# ############################Modbus TCP Test###########################################
    logger.info('Modbus TCP to {} Test in progress'.format(self.address))
    asyncio.run(AsyncModbusTCP(self, self.address)) # Modbus TCP Test

######################Read Register##############################################
    newTest = AccuenergyModbusRequest(self.COM,self.BR)
    newTest.rebootCounter(self) # Check reboot counter
    
    if(self.failCount==0):
      print(success)
    else:
      with shared_failCount.get_lock():
        value = shared_failCount.value
        value += 1
        shared_failCount.value = value
      print(fail)
      parseError2 = ''
      for bugs in self.failTest:
        parseError2 += str(bugs) + ' '
      run('Meter {} Test fails, with {} Errors {}'\
        .format(self.serialNum,self.failCount,parseError2))
      logger.error("Fail {} tests: {}"\
        .format(self.failCount,parseError2))
      #logger.info('Test Failed {}'.format(parseError2))
      self.failTest.append(self.serialNum)
      
    logger.info('General(web2) test completed')
    
#############Config init#####################
if __name__ == '__main__':
    print(starter)

#  Test Procedures         
###########################WEB2 Related######
    # if(not debugMode):
    print('Total core number {}'.format(multiprocessing.cpu_count()))
    jobList = []
    continueAdding = True
    processID = 1
    portList = serial_ports()
    PortOrder = []
    
    while(continueAdding and portList):
      print('Available ports:',portList)
      portNUM = input('Process {} will connect to com port '\
        .format(processID))
      portNUM = 'COM'+portNUM
      if(portNUM in portList):
        continueAdding = True if ('Y'== input('Enter y/Y to add another meter ? ')\
          .upper()) else False
        # input y to add new meter
        processID += 1
        PortOrder.append(portNUM)
        portList.remove(portNUM)
    start_time = time.time()    
    shared_failCount = multiprocessing.Value('i',0)
    openbrowserlock = multiprocessing.Lock()
    openyabelock = multiprocessing.Lock()
    for c,port in enumerate(PortOrder):
      PlugIp = targetIp[c]
      plug = KasaSmartPlug(PlugIp)
      TR = TestRunner(c+1, plug, port)
      process = multiprocessing.Process(target=TR.run_tests, \
                                        args=(shared_failCount,\
                                          openbrowserlock,))
      jobList.append(process)
      
    for j in jobList:
      j.start()
    
    for j in jobList:
      
      j.join()
      
    end_time = time.time()
    runtime = end_time - start_time
    global_error = shared_failCount.value #store total error count for both phase1 and phase2 test
    if(shared_failCount.value == 0):
      print(p1Passed)
      run('ections test finished successfully, total runtime of {}m{}s'\
        .format(int(runtime//60),int(runtime%60)))
      pass
    else:
      print(p1Fail)
      run('Some Meter fail to pass all tests, total runtime of {}m{}s'\
        .format(int(runtime//60),int(runtime%60)))
      pass
    logger.info("Gen. tests finished, runtime: {} minutes {} seconds"\
      .format(int(runtime//60),int(runtime%60)))

    Web2Test = input('Press Enter to continue WEB Push Test ')
    start_time2 = time.time()    
    shared_failCount = multiprocessing.Value('i',0)
    openbrowserlock = multiprocessing.Lock()
    tasks = []
    for c,port in enumerate(PortOrder):
      PlugIp = targetIp[c]
      plug = KasaSmartPlug(PlugIp)
      TR = TestRunner(c+1, plug, port)
      process = multiprocessing.Process(target=TR.run_webpush, \
                                        args=(shared_failCount,\
                                        openbrowserlock,openyabelock,))
      tasks.append(process)
      
    for j in tasks:
      j.start()

    for j in tasks:
      j.join()
      
    end_time2 = time.time()
    runtime2 = end_time2 - start_time2
    prev_error = global_error
    global_error += shared_failCount.value
    
    if(global_error==0):
      if(shared_failCount.value!=0):
        print(p2Fail)      
        run('Some Meter fail to pass all tests, total runtime of {}m{}s'\
          .format(int(runtime//60),int(runtime%60)))
      elif(shared_failCount.value == 0):
        print(allPassed)
        
    else:
      print(fail)  
      run('Some test failed, total runtime of {}m{}s'\
        .format(int(runtime//60),int(runtime%60)))
      pass

    logger.info("Test finished, runtime: {} minutes {} seconds"\
      .format(int(runtime//60),int(runtime%60)))