from time import sleep
from pymodbus.client import ModbusTcpClient
from collections import defaultdict
class touTest():
  #ramdom ModbusTcpClient datetime
  def __init__(self,Host):
    self.TariffReadingRange = {0:29184 ,1:29194, 2: 29204, 3: 29214}
    self.tou = defaultdict(float)
    Tariff = ["Sharp","Peak","Valley","Normal"]
    Parameters = ["Ep_imp","Ep_exp","Eq_imp","Eq_exp","Es"]
    for tariffName in Tariff:
      for parameters in Parameters:
        self.tou[tariffName+'_'+parameters] = 0
    
    self.HolidayStart = 31376
    self.Host = Host
    self.Season = {30752:[1,1,1],30755:[2,1,2],30758:[3,1,3],30761:[4,1,4],30764:[5,1,5],30767:[6,1,6],30770:[7,1,7],30773:[8,1,8],30776:[9,1,9],30779:[10,1,10],30782:[11,1,11],30785:[12,1,12]}
    self.Schedule = {30788:[9,0,0],30791:[15,0,1],\
                    30830:[9,0,0],30833:[15,0,1],\
                    30872:[9,0,0],30875:[15,0,1],\
                    30914:[9,0,0],30917:[15,0,1],\
                    30956:[9,0,0],30959:[15,0,1],\
                    30998:[9,0,0],31001:[15,0,1],\
                    31040:[9,0,0],31043:[15,0,1],\
                    31082:[9,0,0],31085:[15,0,1],\
                    31124:[9,0,0],31127:[15,0,1],\
                    31166:[9,0,0],31169:[15,0,1],\
                    31208:[9,0,0],31211:[15,0,1],\
                    31250:[9,0,0],31253:[15,0,1],\
                    31292:[9,0,2],31295:[15,0,3],\
                    31334:[9,0,3],31337:[15,0,2]
                    } #Sharp ->1; Peak ->2; Valley ->3; Normal -> 4 CURRENTLY 14 schedules, SUBJECT TO CHANGE IF NEEDED
    
    self.Schedule2Tariff = {
      1:(9,0,0,15,0,1)\
      ,2:(9,0,0,15,0,1)\
        ,3:(9,0,0,15,0,1)\
          ,4:(9,0,0,15,0,1)\
            ,5:(9,0,0,15,0,1)\
              ,6:(9,0,0,15,0,1)\
                ,7:(9,0,0,15,0,1)\
                  ,8:(9,0,0,15,0,1)\
                    ,9:(9,0,0,15,0,1)\
                      ,10:(9,0,0,15,0,1)\
                        ,11:(9,0,0,15,0,1)\
                          ,12:(9,0,0,15,0,1)\
                           ,13:(9,0,2,15,0,3)\
                             ,14:(9,0,3,15,0,2)
                             }
    # self.touEnergy = {'sharp':[x for x in range()]}
    self.seasonList = []
    self.specialDate = [[1,1,14],[2, 19, 14], [2, 22, 14], [3, 1, 14], [3, 10, 14],\
      [3, 17, 14], [3, 20, 14], [3, 21, 14], [4, 21, 14], [5, 1, 14], [7, 7, 14],\
        [7, 11, 14], [7, 23, 14], [7, 28, 14], [8, 1, 14], [8, 2, 14], [8, 7, 14],\
          [8, 20, 14], [9, 20, 14], [10, 4, 14], [10, 5, 14], [10, 6, 14],  [10, 22, 14], [10, 24, 14],\
            [11, 10, 14], [11, 19, 14], [11, 22, 14], [12, 2, 14], [12, 10, 14], [12, 20, 14], [12, 27, 14]]
  
  def syncConnectWrite(self,Address,Value, promptEnable=False):
    client = ModbusTcpClient(host = self.Host)
    client.connect()
    if(promptEnable):
      print('Sync Connection Status: {}'.format(client.connected))
    client.write_registers(Address,Value,slave=1)
    client.close()
    
  def syncConnectRead(self,Address,Count, promptEnable=False):
    client = ModbusTcpClient(host = self.Host)
    try:
        client.connect()
        #print('Sync Connection Status: {}'.format(client.connected))
        assert client.connected
    except AssertionError:
        return -1
    rr = client.read_holding_registers(Address,Count,slave=1)
    client.close()
    if(len(rr.registers)==2):
        rrlow = format(int(rr.registers[-1]),'02X')
        rrhigh =format(int(rr.registers[0]),'02X') #cast to fixed length 0xAB
        energy = int(rrhigh+rrlow,16)
        return energy
    return rr.registers[-1]


  def touConfig(self):    
    for scheduleId in self.Schedule: #SCHEDULES
      self.syncConnectWrite(scheduleId,self.Schedule[scheduleId])
    
    self.syncConnectWrite(30721,[14]) # 14 schedules
    
    for seasonId in self.Season: # SEASONS
      self.syncConnectWrite(seasonId,self.Season[seasonId])
      self.seasonList.append(self.Season[seasonId])
    self.syncConnectWrite(30720,[12]) # 12 seasons

    holiday_start = self.HolidayStart
    for InfoList in self.specialDate:#HOLIDAYS
      self.syncConnectWrite(holiday_start,InfoList)
      holiday_start += 3 #next header
    
    self.seasonList = sorted(self.seasonList)
    print('Holiday date',len(self.specialDate),self.specialDate,'\n',\
    'Season date:',len(self.seasonList), self.seasonList)
    self.syncConnectWrite(30726,[30]) # 30 holidays
    self.syncConnectWrite(30727,[1]) # enable TOU
    
    if(self.syncConnectRead(30734,1) == -1):
        return False
    else:
        return True
    
  def checkTouEnergy(self,TariffIndex:int,sleeptime:int):
    #print(TariffIndex)
    start_address = self.TariffReadingRange[TariffIndex]+8
    start_reading = self.syncConnectRead(start_address,2)
    sleep(sleeptime)
    end_reading = self.syncConnectRead(start_address,2)
    energyAccumulated = (end_reading-start_reading)/10 
    expectedEnergy = 60*energyAccumulated*(60/sleeptime)
    if(expectedEnergy-18000)>100:
        print('Accumulated: {} Ref:{}'.format(expectedEnergy,18000))
    else:
        print('Pased: {} Ref:{}'.format(expectedEnergy,18000))
    if(TariffIndex==0):
        print('Sharp Apparent Energy Accumulated: {} kVA'.format(energyAccumulated))
    elif(TariffIndex==1):
        print('Peak Apparent Energy Accumulated: {} kVA'.format(energyAccumulated))
    elif(TariffIndex==2):
        print('Valley Apparent Energy Accumulated: {} kVA'.format(energyAccumulated))
    elif(TariffIndex==3):
        print('Normal Apparent Energy Accumulated: {} kVA'.format(energyAccumulated))
  
  def writeSingleDayClock(self,date):
    print('On date ',date)
    thisTime = date
    thisSchedule = thisTime[-1] # desired schedule
    thisDetailSchedule = self.Schedule2Tariff[thisSchedule] # (hr,min,tariff,hr2,min2,tariff2)
    #print(thisDetailSchedule)
    currDate = [2023]+[thisTime[0]]+[thisTime[1]]+[0,0,0] # year, month, day, [hr, min, sec]
                                                            # 0      1      2     3   4    5
    sleepTime = 5
    TariffIndex = thisDetailSchedule[5]
    self.syncConnectWrite(4160,currDate) # update meter clock 
    self.checkTouEnergy(TariffIndex,sleepTime)
    currDate[3] = 9
    TariffIndex = thisDetailSchedule[2]
    self.syncConnectWrite(4160,currDate) # update meter clock 
    self.checkTouEnergy(TariffIndex,sleepTime)
    sleep(5)
    
    currDate[3] = 15
    TariffIndex = thisDetailSchedule[5]
    self.syncConnectWrite(4160,currDate) # update meter clock 
    self.checkTouEnergy(TariffIndex,sleepTime)
    sleep(5)

    #Depend on presentDate, this function will set the meter's clock to the desired date, starting from 
  def smartClock(self,presentDate=None):
    if(not presentDate): #check whole year's schedule
      while(self.seasonList and self.specialDate):
          print('Season List ',self.seasonList[0][:-1],'Holiday List',self.specialDate[0][:-1])
          if(self.seasonList[0][:-1] < self.specialDate[0][:-1]):
              # this date is a regular schedule
              thisTime = self.seasonList[0]
              self.seasonList = self.seasonList[1:] # popleft, update the list
              self.writeSingleDayClock(thisTime)
              #currDate[3] += 1 # move-forward by one hour

          elif(self.seasonList[0][:-1] == self.specialDate[0][:-1]): # case 2 when season start date and holiday date is the same, holiday has higher priority
              self.seasonList[0][1] += 1 # push season start date to next day
              thisTime = self.specialDate[0]
              self.specialDate = self.specialDate[1:] # popleft, update the list
              self.writeSingleDayClock(thisTime)
              
          else:
              thisTime = self.specialDate[0]
              self.specialDate = self.specialDate[1:] # popleft, update the list
              self.writeSingleDayClock(thisTime)
              
      while(self.specialDate):
          thisTime = self.specialDate[0]
          self.specialDate = self.specialDate[1:] # popleft, update the list
          self.writeSingleDayClock(thisTime)
          
      while(self.seasonList):
          thisTime = self.seasonList[0]
          self.seasonList = self.seasonList[1:] # popleft, update the list
          self.writeSingleDayClock(thisTime)
                
    else: #provide a specific date
        print(presentDate)
        self.writeSingleDayClock(presentDate)
    if(self.failCount==0):
      return True
    else:
      return False
        
        
  def touTestMain(self):
    self.touConfig()
    self.smartClock()

if __name__ == '__main__':
    tou_Test = touTest("192.168.60.110")
    #touTest.setTouSeasonHoliday()
    print(tou_Test.touConfig())
    tou_Test.touTestMain()